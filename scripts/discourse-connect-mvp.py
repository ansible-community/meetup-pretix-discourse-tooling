#!/usr/bin/env python3
"""DiscourseConnect consumer - v2 test toolkit (single file, Flask).

Target  : https://forum.ansible.com

v2 policy
---------
* Login always requests `require_2fa=true`.
* After a verified SSO exchange we enrich from the Discourse ADMIN API
  (/admin/users/{id}.json) with an admin read-only API key:
      - silenced / suspended / staged / trust_level / groups / badges
* A user is BLOCKED if any of:
      silenced (muted)                 -> "blocked: moderation (silenced)"
      suspended                        -> "blocked: suspended"  (rare: SSO shouldn't reach here)
      RTBF / anonymised email pattern  -> "blocked: RTBF (anonymised)"
      privileged (meetup-staff OR meetup-organisers-{city}) without confirmed_2fa=true
                                       -> "blocked: DiscourseConnect did not confirm 2FA"
* Otherwise permission (highest wins): admin > host(city list) > regular.
* Regular users can always log in (every Discourse user can buy a ticket).

Endpoints:
  /            landing: login link + last analysis summary
  /login       start SSO with required 2FA
  /callback    verify sig + nonce -> analyse -> summary (+ always show raw payload)
  /debug       dump last payload, admin API JSON, session, config
  /logout      clear local session

Env:
  DISCOURSE_SSO_SECRET     (required) provider secret string
  DISCOURSE_API_KEY        (optional for this diagnostic tool; required by the Pretix plugin)
  CALLBACK_URL             http://localhost:5000/callback (default)
  FLASK_SECRET             fixed dev secret (sessions survive restarts)

Run:
  export DISCOURSE_SSO_SECRET='...'
  export DISCOURSE_API_KEY='...'
  python mvp.py
"""

import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import urllib.parse
import urllib.request
from typing import Any

from flask import Flask, redirect, render_template_string, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "dev-only-secret-change-me-0123456789")
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=False)

DISCOURSE_BASE_URL = "https://forum.ansible.com"
SSO_SECRET = os.environ["DISCOURSE_SSO_SECRET"]  # required, fails fast
CALLBACK_URL = os.environ.get("CALLBACK_URL", "http://localhost:5000/callback")
API_KEY = os.environ.get("DISCOURSE_API_KEY")
API_USER = "system"
REQUIRE_2FA = True
STAFF_GROUP = "meetup-staff"
ORGANIZERS_GROUP_RE = re.compile(r"^meetup-organisers-([a-z]+)$")
MEETUP_KEYWORD = "meetup"

_last = {"status": "no callback yet", "payload": {}, "summary": {}, "admin_api": {}}

# ------------------------------------------------------------------ protocol --


def sign(b64: bytes) -> str:
    return hmac.new(SSO_SECRET.encode(), b64, hashlib.sha256).hexdigest()


def build_sso_url(nonce: str) -> str:
    fields = {"nonce": nonce, "return_sso_url": CALLBACK_URL}
    if REQUIRE_2FA:
        fields["require_2fa"] = "true"
    raw = urllib.parse.urlencode(fields)
    b64 = base64.b64encode(raw.encode("utf-8"))
    sig = sign(b64)
    sso = urllib.parse.quote(b64.decode("ascii"))
    return f"{DISCOURSE_BASE_URL}/session/sso_provider?sso={sso}&sig={sig}"


def decode_payload(sso: str, sig: str):
    sso_b64 = urllib.parse.unquote(sso).encode("ascii")
    if not sig or not hmac.compare_digest(sign(sso_b64), sig):
        return None, "signature mismatch"
    try:
        data = {k: v[0] for k, v in urllib.parse.parse_qs(base64.b64decode(sso_b64).decode("utf-8")).items()}
    except Exception as exc:
        return None, f"decode failed: {exc}"
    return data, "signature OK"


# -------------------------------------------------------------- API (optional) --


def api_json(path: str) -> dict[str, Any] | None:
    """Read-only Discourse API call; returns dict or None. Never blocks the flow."""
    if not API_KEY:
        return None
    req = urllib.request.Request(
        DISCOURSE_BASE_URL + path,
        headers={
            "Api-Key": API_KEY,
            "Api-Username": API_USER,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception as exc:
        return {"__error__": f"{exc}"}


def fetch_badges(username: str) -> list:
    data = api_json(f"/user-badges/{urllib.parse.quote(username)}.json")
    if not data:
        return []
    name_by_id = {b["id"]: b["name"] for b in data.get("badges", []) if "id" in b}
    return [name_by_id.get(ub.get("badge_id"), "?") for ub in data.get("user_badges", [])]


def fetch_admin_user(external_id: str) -> dict:
    data = api_json(f"/admin/users/{urllib.parse.quote(str(external_id))}.json")
    if not data:
        return {}
    return data.get("user", data)


RTBF_EMAIL_SUFFIX = "@anonymized.invalid"


def is_anonymised(data: dict) -> bool:
    """RTBF detection: email-domain only (matches Discourse UserAnonymizer::EMAIL_SUFFIX)."""
    email = (data.get("email") or "").lower()
    return email.endswith(RTBF_EMAIL_SUFFIX)


def is_silenced(api_data: dict) -> bool:
    """Check silenced_till (datetime, present only when silenced)."""
    return bool(api_data.get("silenced_till"))


def is_suspended(api_data: dict) -> bool:
    """Check suspended_till (datetime, present only when suspended)."""
    return bool(api_data.get("suspended_till"))


# ----------------------------------------------------------------- analysis --


def analyse(data: dict) -> dict:
    external_id = data.get("external_id", "")
    groups_set = {g for g in data.get("groups", "").split(",") if g}
    organiser_groups = sorted(g for g in groups_set if ORGANIZERS_GROUP_RE.fullmatch(g))
    cities = [ORGANIZERS_GROUP_RE.fullmatch(g).group(1) for g in organiser_groups]
    meetup_groups = sorted(g for g in groups_set if MEETUP_KEYWORD in g.lower())

    is_admin = STAFF_GROUP in groups_set
    is_mod = data.get("moderator") == "true"
    privileged = is_admin or bool(organiser_groups)

    # Admin API enrichment (only when API key set)
    api = fetch_admin_user(external_id)
    _last["admin_api"] = api
    twofa_enabled = api.get("second_factor_enabled")
    twofa_known = twofa_enabled is not None
    confirmed_2fa = data.get("confirmed_2fa") == "true"
    silenced = is_silenced(api)
    silenced_till = api.get("silenced_till")
    suspended = is_suspended(api)
    staged = bool(api.get("staged"))
    trust_level = api.get("trust_level")
    api_groups = sorted(set(api.get("secondary_group_names", []) or []))

    badges = fetch_badges(data.get("username", ""))
    meetup_badges = sorted(b for b in badges if MEETUP_KEYWORD in b.lower())

    rtbf = is_anonymised(data)

    reasons, blocked = [], False
    if silenced:
        blocked = True
        reasons.append("moderation: silenced" + (f" until {silenced_till}" if silenced_till else ""))
    if suspended:
        blocked = True
        reasons.append(
            "moderation: suspended" + (f" until {api.get('suspended_till')}" if api.get("suspended_till") else "")
        )
    if rtbf:
        blocked = True
        reasons.append("RTBF: anonymised (block future ticket purchase)")
    if privileged and not confirmed_2fa:
        blocked = True
        reasons.append("privileged but DiscourseConnect did not confirm 2FA")

    if blocked:
        permission = "blocked"
    elif is_admin:
        permission = "admin"
    elif organiser_groups:
        permission = "host (" + ", ".join(cities) + ")"
    else:
        permission = "regular"

    return {
        "external_id": external_id,
        "username": data.get("username"),
        "email": data.get("email"),
        "name": data.get("name"),
        "admin": is_admin,
        "moderator": is_mod,
        "avatar_url": data.get("avatar_url"),
        "all_groups": sorted(groups_set),
        "api_groups": api_groups,
        "meetup_groups": meetup_groups,
        "organiser_groups": organiser_groups,
        "cities": cities,
        "badges": badges,
        "meetup_badges": meetup_badges,
        "second_factor_enabled": twofa_enabled,
        "twofa_known": twofa_known,
        "confirmed_2fa": confirmed_2fa,
        "silenced": silenced,
        "silenced_till": silenced_till,
        "suspended": suspended,
        "staged": staged,
        "trust_level": trust_level,
        "rtbf": rtbf,
        "privileged": privileged,
        "blocked_reasons": reasons,
        "permission": permission,
        "api_configured": bool(API_KEY),
    }


# ----------------------------------------------------------------- templates --

PAGE = """<html><body style="font-family:sans-serif">
<h1>DiscourseConnect test toolkit <small>(forum.ansible.com)</small></h1>
<p><a href="/login">Sign in with Discourse</a>
{% if require_2fa %}<b>[REQUIRE_2FA=on]</b>{% endif %}</p>

{% if s %}
<h2 style="color:
{% if s.permission == 'blocked' %}red
{% elif s.permission == 'admin' %}purple
{% elif s.permission.startswith('host') %}blue
{% else %}green{% endif %}">Final permission: {{ s.permission }}</h2>
{% if s.blocked_reasons %}<p><b>Blocked because:</b> {{ s.blocked_reasons|join('; ') }}</p>{% endif %}

<table border="1" cellpadding="6">
<tr><td>external_id</td><td>{{ s.external_id }}</td></tr>
<tr><td>username</td><td>{{ s.username }}</td></tr>
<tr><td>email</td><td>{{ s.email }}</td></tr>
<tr><td>name</td><td>{{ s.name }}</td></tr>
<tr><td>admin / moderator</td><td>{{ s.admin }} / {{ s.moderator }}</td></tr>
<tr><td>privileged</td><td>{{ s.privileged }}</td></tr>
<tr><td>avatar_url</td><td>{{ s.avatar_url }}</td></tr>
<tr><td>all groups (payload)</td><td>{{ s.all_groups|join(', ') }}</td></tr>
<tr><td>groups (admin API)</td><td>{{ s.api_groups|join(', ') or '(n/a)' }}</td></tr>
<tr><td>meetup groups</td><td>{{ s.meetup_groups|join(', ') or '(none)' }}</td></tr>
<tr><td>organiser groups</td><td>{{ s.organiser_groups|join(', ') or '(none)' }}</td></tr>
<tr><td>cities</td><td>{{ s.cities|join(', ') or '(none)' }}</td></tr>
<tr><td>badges</td><td>{{ s.badges|join(', ') or '(none)' }}</td></tr>
<tr><td>meetup badges</td><td>{{ s.meetup_badges|join(', ') or '(none)' }}</td></tr>
<tr><td>silenced / suspended staged</td><td>{{ s.silenced }} / {{ s.suspended }} / {{ s.staged }}</td></tr>
<tr><td>silenced until</td><td>{{ s.silenced_till }}</td></tr>
<tr><td>trust_level</td><td>{{ s.trust_level }}</td></tr>
<tr><td>2FA enabled (account)</td><td>{{ s.second_factor_enabled }}{% if not s.api_configured %} <b>(API not configured)</b>{% endif %}</td></tr>
<tr><td>RTBF / anonymised</td><td>{{ s.rtbf }}</td></tr>
</table>
{% endif %}

<h3>Raw payload from Discourse</h3>
<table border="1" cellpadding="6">
{% for k, v in rows %}<tr><td><b>{{ k }}</b></td><td>{{ v }}</td></tr>{% endfor %}
</table>
<p><a href="/debug">Debug state</a> &middot; <a href="/logout">Forget sign-in</a></p>
</body></html>"""


def rows_of(d: dict):
    return sorted((k, v) for k, v in d.items())


@app.route("/")
def home():
    return render_template_string(
        PAGE,
        require_2fa=REQUIRE_2FA,
        s=_last.get("summary"),
        rows=rows_of(_last.get("payload", {})),
    )


@app.route("/login")
def login():
    session["discourse_nonce"] = secrets.token_urlsafe(32)
    return redirect(build_sso_url(session["discourse_nonce"]))


@app.route("/callback")
def callback():
    data, status = decode_payload(request.args.get("sso", ""), request.args.get("sig", ""))
    _last["status"] = status
    _last["payload"] = data or {}
    if not data:
        return f"<h1>403 - {html.escape(status)}</h1><p><a href='/login'>Try again</a></p>", 403
    if data.get("failed") == "true":
        _last["status"] = "failed=true from Discourse"
        return "<h1>failed=true</h1><p><a href='/login'>Try again</a></p>", 401

    stored = session.pop("discourse_nonce", None)
    if not stored or not hmac.compare_digest(data.get("nonce", ""), stored):
        return (
            "<h1>403 - bad or replayed nonce</h1><p><a href='/login'>Fresh attempt</a></p>",
            403,
        )

    s = analyse(data)
    _last["summary"] = s
    _last["status"] = f"OK - {s['username']} ({s['external_id']}) -> {s['permission']}"
    return render_template_string(PAGE, require_2fa=REQUIRE_2FA, s=s, rows=rows_of(data))


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/debug")
def debug():
    return "<pre>" + html.escape(json.dumps(_last, indent=2, default=str)) + "</pre><p><a href='/'>Home</a></p>"


if __name__ == "__main__":
    print("Login page : http://localhost:5000/")
    print(f"Target     : {DISCOURSE_BASE_URL}")
    print(f"Callback   : {CALLBACK_URL}")
    print(f"API key    : {'SET' if API_KEY else 'NOT set (2FA/status checks show unknown)'}")
    print(f"REQUIRE_2FA (challenge mode): {REQUIRE_2FA}")
    app.run(host="127.0.0.1", port=5000, debug=False)
