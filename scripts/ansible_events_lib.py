from __future__ import annotations

import dataclasses
import logging
import os
import sys
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ansible_meetups")

ApiResponse = dict[str, Any] | bool | None

# --- Secrets (from environment) ---
PRETIX_URL = os.environ.get("PRETIX_URL", "http://localhost:8000")
PRETIX_API_TOKEN = os.environ.get("PRETIX_API_TOKEN")
DISCOURSE_API_KEY = os.environ.get("DISCOURSE_API_KEY")

# --- Ansible Community constants ---
DISCOURSE_URL = "https://forum.ansible.com"
DISCOURSE_API_USER = "system"
ORGANIZER_SLUG = "ansible-meetups"
CONTACT_EMAIL = "ansible-community-events@redhat.com"
ANSIBLE_PRIMARY_COLOR = "#EE0000"
CODE_OF_CONDUCT_URL = "https://docs.ansible.com/ansible/devel/community/code_of_conduct.html"
PRIVACY_POLICY_URL = f"{DISCOURSE_URL}/privacy"
EVENTS_FORUM_URL = f"{DISCOURSE_URL}/c/events/8"

# --- Discourse IDs ---
DISCOURSE_PARENT_CATEGORY_ID = 8
DISCOURSE_EVENTS_CATEGORY_ID = 14

# --- Naming ---
EVENT_NAME_PREFIX = "Ansible Meetup"
ORGANISER_TEAM_PREFIX = "Ansible Meetup Organisers"
HOST_GROUP_PREFIX = "meetup-host"
ATTENDEE_GROUP_PREFIX = "meetup-attendee"
ADMIN_GROUP_NAME = "meetup-admin"
MIGRATED_GROUP_NAME = "meetup-attendee-migrated"

# --- Pretix template ---
TEMPLATE_SLUG = "ansible-meetup-template-v6"
DEFAULT_ITEM_NAME = "RSVP"
DEFAULT_ITEM_PRICE = "0.00"
DEFAULT_QUOTA_NAME = "Capacity"
ORGANISER_PERMISSIONS: list[str] = [
    "event.orders:read",
    "event.orders:checkin",
]

# --- Discourse user field ---
USER_CITY_FIELD_NAME = "user_event_cities"
USER_CITY_FIELD_ID = 4

# --- Security ---
RTBF_EMAIL_SUFFIX = "@anonymized.invalid"


@dataclasses.dataclass(frozen=True, slots=True)
class CityInfo:
    """A meetup city with its geographic and timezone metadata."""

    region: str
    country: str
    city: str
    timezone: str

    @property
    def slug(self) -> str:
        return self.city.lower().replace(" ", "-")

    @property
    def field_value(self) -> str:
        """Format as 'region:country:city' for Discourse user fields."""
        return f"{self.region}:{self.country}:{self.city}"

    @property
    def event_name(self) -> str:
        return f"{EVENT_NAME_PREFIX} {self.city}"

    @property
    def team_name(self) -> str:
        return f"{ORGANISER_TEAM_PREFIX} - {self.city}"

    @property
    def host_group(self) -> str:
        return f"{HOST_GROUP_PREFIX}-{self.slug}"

    @property
    def attendee_group(self) -> str:
        return f"{ATTENDEE_GROUP_PREFIX}-{self.slug}"


CITIES: tuple[CityInfo, ...] = (
    CityInfo(region="Europe", country="UK", city="London", timezone="Europe/London"),
    CityInfo(region="Europe", country="Spain", city="Barcelona", timezone="Europe/Madrid"),
    CityInfo(region="Europe", country="UK", city="FakeTown", timezone="Europe/London"),
)


def get_city(name: str) -> CityInfo | None:
    """Look up a city by name (case-insensitive). Returns None if not found."""
    for c in CITIES:
        if c.city.lower() == name.lower():
            return c
    return None


TEMPLATE_PLUGINS: list[str] = [
    "pretix.plugins.sendmail",
    "pretix.plugins.ticketoutputpdf",
    "pretix.plugins.checkinlists",
    "pretix.plugins.pretixdroid",
    "pretix.plugins.webcheckin",
    "pretix.plugins.statistics",
    "pretix.plugins.badges",
    "pretix_passbook",
]


def discourse_user_exists(username: str) -> bool:
    """Check whether a Discourse user exists by username."""
    resp = discourse_req("GET", f"u/{username}.json")
    return resp is not None and isinstance(resp, dict)


def discourse_user_in_group(username: str, group_name: str) -> bool:
    """Check whether a Discourse user is a member of a specific group."""
    resp = discourse_req("GET", f"u/{username}.json")
    if not resp or not isinstance(resp, dict):
        return False
    user_data = resp.get("user", {})
    groups = user_data.get("groups", [])
    return any(g.get("name", "").lower() == group_name.lower() for g in groups)


def pre_flight_checks(*, require_discourse: bool = True) -> None:
    """Validate required API environment variables are set.

    Args:
        require_discourse: When False, skip the DISCOURSE_API_KEY check
            (for scripts that only use Pretix).
    """
    missing = []
    if not PRETIX_API_TOKEN:
        missing.append("PRETIX_API_TOKEN")
    if require_discourse and not DISCOURSE_API_KEY:
        missing.append("DISCOURSE_API_KEY")
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def pretix_req(method: str, endpoint: str, payload: dict[str, Any] | None = None) -> ApiResponse:
    """Make an authenticated Pretix API request.

    Returns the parsed JSON dict on success, True for empty-body success
    (e.g. 204), or None on failure.
    """
    url = f"{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/{endpoint}"
    if "?" in url:
        base, query = url.split("?", 1)
        if not base.endswith("/"):
            base += "/"
        url = f"{base}?{query}"
    else:
        if not url.endswith("/"):
            url += "/"

    headers = {
        "Authorization": f"Token {PRETIX_API_TOKEN}",
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.request(method, url, json=payload, headers=headers, timeout=10)
    except httpx.HTTPError as exc:
        logger.error("Pretix %s %s connection error: %s", method, endpoint, exc)
        return None
    if resp.status_code not in (200, 201, 204):
        logger.error("Pretix %s %s failed: %s %s", method, endpoint, resp.status_code, resp.text[:200])
        return None
    if not resp.text:
        return True
    try:
        return resp.json()
    except ValueError:
        logger.error("Pretix %s %s returned invalid JSON", method, endpoint)
        return None


def discourse_req(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    run_as: str | None = None,
) -> ApiResponse:
    """Make an authenticated Discourse API request.

    Args:
        run_as: Override the API username for this request (e.g. to post
            on behalf of a specific user).

    Returns the parsed JSON dict on success, True for empty-body success,
    or None on failure.
    """
    url = f"{DISCOURSE_URL.rstrip('/')}/{endpoint}"
    headers = {
        "Api-Key": DISCOURSE_API_KEY,
        "Api-Username": run_as or DISCOURSE_API_USER,
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.request(method, url, json=payload, headers=headers, timeout=10)
    except httpx.HTTPError as exc:
        logger.error("Discourse %s %s connection error: %s", method, endpoint, exc)
        return None
    if resp.status_code not in (200, 201, 204):
        if "has already been taken" not in resp.text:
            logger.error("Discourse %s %s failed: %s %s", method, endpoint, resp.status_code, resp.text[:200])
        return None
    if not resp.text:
        return True
    try:
        return resp.json()
    except ValueError:
        logger.error("Discourse %s %s returned invalid JSON", method, endpoint)
        return None


def pretix_list_all(endpoint: str) -> list[dict[str, Any]]:
    """Fetch all results from a paginated Pretix list endpoint."""
    results: list[dict[str, Any]] = []
    resp = pretix_req("GET", endpoint)
    while resp and isinstance(resp, dict):
        results.extend(resp.get("results", []))
        next_url = resp.get("next")
        if not next_url:
            break
        try:
            page_resp = httpx.get(
                next_url,
                headers={"Authorization": f"Token {PRETIX_API_TOKEN}", "Content-Type": "application/json"},
                timeout=10,
            )
            resp = page_resp.json() if page_resp.status_code == 200 else None
        except (httpx.HTTPError, ValueError):
            break
    return results


def check_event_exists(slug: str) -> bool:
    """Check whether a Pretix event exists by slug. Returns False on error."""
    url = f"{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/events/{slug}/"
    headers = {"Authorization": f"Token {PRETIX_API_TOKEN}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
    except httpx.HTTPError as exc:
        logger.error("Pretix check_event_exists %s connection error: %s", slug, exc)
        return False
    return resp.status_code == 200


def strip_discourse_block(markdown: str) -> str:
    """Strip Discourse-only content above the first --- separator."""
    return markdown.split("---", 1)[1].strip() if "---" in markdown else markdown
