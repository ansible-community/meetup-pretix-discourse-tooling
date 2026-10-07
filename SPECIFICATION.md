# Technical Specification: Ansible Community Events Platform

---

## 1. Executive Summary

The Ansible Community Events Platform replaces Meetup Pro (`meetup.com/pro/ansible`) with community-owned infrastructure for managing global Ansible meetups. It integrates two external systems:

- **Pretix** (self-hosted, open-source): Event ticketing, RSVP, QR code generation, check-in, and attendee management. Pretix stores no passwords and has no native user registration.
- **Discourse** (`forum.ansible.com`): Identity provider (SSO), community discussion, event agenda hosting, group permissions, and moderation. Discourse is the single source of truth for user identity.

The platform provides:

1. **Zero-friction RSVP** for free community meetups via Discourse SSO into Pretix.
2. **Regional isolation** so local organizers can only see their own city's attendee data.
3. **Template-driven consistency** so every meetup worldwide has identical checkout settings, branding, and QR code delivery.
4. **Community-first event pages** where the Discourse forum topic IS the event page, and Pretix is the invisible ticketing backend.
5. **Automated social media promotion** with ready-to-paste copy for 6 platforms.

The system is operated by the Ansible Community Team via CLI scripts. Local organizers interact only through the Discourse forum (to manage event content) and the Pretix dashboard (to view attendees and check in at the door).

---

## 2. System Context

### External Systems

| System | Role | API | Auth |
|---|---|---|---|
| **Pretix** | Event ticketing, RSVP, QR codes, check-in | REST API v1 (`/api/v1/`) | Token-based (`Authorization: Token {token}`) |
| **Discourse** | Identity (SSO), forum, group permissions, event content | REST API (`/posts.json`, `/admin/groups.json`, etc.) | Global API key (`Api-Key` + `Api-Username` headers) |

### Trust Model

- Discourse is the **single source of truth** for identity. Pretix's `NativeAuthBackend` is disabled.
- All user authentication flows through DiscourseConnect (HMAC-SHA256 SSO). Pretix stores the Discourse `external_id` as the identity key.
- API tokens (`PRETIX_API_TOKEN`, `DISCOURSE_API_KEY`) are operator secrets. They are never embedded in URLs, logged in error output, or exposed to end users.
- The Discourse API key has global admin scope. The `Api-Username` header determines which user the action is performed as (impersonation via `run_as`).

### Operator Model

| Actor | Access | How |
|---|---|---|
| **Ansible Community Team** | Full: create events, manage templates, run all scripts | CLI scripts + API tokens |
| **Local Organizer** | Scoped: view attendees + check in for their city only | Discourse SSO → Pretix dashboard (mapped via `meetup-organisers-{city}` group → Pretix Team) |
| **Attendee** | RSVP only: register for events, receive QR code | Discourse SSO → Pretix checkout |

### Environment Variables

| Variable | Required By | Default | Purpose |
|---|---|---|---|
| `PRETIX_URL` | All scripts | `http://localhost:8000` | HTTPS required except localhost/loopback development URLs |
| `PRETIX_API_TOKEN` | All scripts | *(none — required)* | Pretix API authentication |
| `DISCOURSE_URL` | All scripts | `https://forum.ansible.com` | Discourse instance base URL |
| `DISCOURSE_API_KEY` | All scripts | *(none — required)* | Discourse API authentication |
| `DISCOURSE_API_USER` | All scripts | `system` | Default Discourse API username |
| `DISCOURSE_SSO_SECRET` | SSO toolkit only | *(none — required)* | HMAC shared secret for DiscourseConnect |
| `DISCOURSE_BASE_URL` | SSO toolkit only | `https://forum.ansible.com` | SSO redirect target |
| `CALLBACK_URL` | SSO toolkit only | `http://localhost:5000/callback` | SSO return URL |
| `FLASK_SECRET` | SSO toolkit only | `dev-only-secret-change-me-0123456789` | Flask session signing key |
| `DISCOURSE_API_USERNAME` | SSO toolkit only | `system` | Admin user for enrichment queries |
| `MEETUP_KEYWORD` | SSO toolkit only | `meetup` | Keyword for meetup-related group/badge filtering |

---

## 3. Data Models

### 3.1 CityInfo

A frozen, slotted dataclass representing a meetup city.

**Fields:**

| Field | Type | Example | Description |
|---|---|---|---|
| `region` | `str` | `"Europe"` | Geographic region |
| `country` | `str` | `"UK"` | Country name or code |
| `city` | `str` | `"London"` | Display name of the city |
| `timezone` | `str` | `"Europe/London"` | IANA timezone identifier |

**Derived Properties:**

| Property | Derivation | Example |
|---|---|---|
| `slug` | `city.lower().replace(" ", "-")` | `"london"` |
| `field_value` | `f"{region}:{country}:{city}"` | `"Europe:UK:London"` |

**Current Registry (immutable tuple):**

| Region | Country | City | Timezone |
|---|---|---|---|
| Europe | UK | London | Europe/London |
| Europe | Spain | Barcelona | Europe/Madrid |
| Europe | UK | FakeTown | Europe/London |

**Constraints:**
- The registry is an immutable `tuple[CityInfo, ...]`. No duplicate city names.
- All timezones must contain a `/` (IANA format validation).
- CityInfo instances are frozen — no attribute mutation after construction.

### 3.2 API Results and Errors

`pretix_req` and `discourse_req` return `dict[str, Any]` for JSON responses and `{}` for successful empty responses. Network errors, non-success status codes, invalid JSON, and non-object JSON raise `ApiError`; they are never represented as `None` or `False`. The CLI boundary catches `ApiError`, reports a concise failure, and exits non-zero. `check_event_exists` returns a boolean only for confirmed HTTP `200` or `404` responses.

### 3.3 Master Template

A hidden Pretix event (`ansible-meetup-template-v6`) that is never published. All new meetup events are cloned from it via the Pretix API's `clone_from` parameter.

**Template Settings (enforced on every run of day0):**

| Setting | Value | Purpose |
|---|---|---|
| `max_items_per_order` | `1` | One RSVP per person |
| `invoice_address_asked` | `False` | Free events — no billing |
| `attendee_names_asked` | `True` | Collect real name at checkout |
| `attendee_names_required` | `True` | Name is mandatory |
| `attendee_emails_asked` | `False` | Email comes from SSO |
| `name_scheme` | `"full"` | Single name field (not given/family) |
| `order_email_asked_twice` | `False` | No email confirmation step |
| `payment_term_last` | `null` | No payment deadline (free) |
| `checkout_show_copy_answers_button` | `False` | Irrelevant with max 1 item |

**Template Event Properties:**

| Property | Value |
|---|---|
| Slug | `ansible-meetup-template-v6` |
| Name | `TEMPLATE: Standard Meetup` |
| Live | `False` (never published) |
| Currency | `USD` |
| Plugins | `pretix.plugins.sendmail`, `pretix.plugins.ticketoutputpdf` |
| Default Item | `RSVP` — price `0.00`, `active: True`, `admission: True` |
| Default Quota | `Capacity` — size `100`, linked to RSVP item |

### 3.4 Naming Conventions

| Entity | Pattern | Example |
|---|---|---|
| Discourse staff group | `meetup-staff` | `meetup-staff` |
| Discourse organiser group | `meetup-organisers-{slug}` | `meetup-organisers-london` |
| Discourse attendee group | `meetup-attendee-{slug}` | `meetup-attendee-london` |
| Discourse category | City name under parent category | `London` (child of Events, ID 8) |
| Pretix team | `Ansible Meetup Organisers - {City}` | `Ansible Meetup Organisers - London` |
| Pretix event slug | `{slug}-{mon}-{yyyy}` | `london-oct-2026` |
| Forum topic title | `Ansible Meetup: {City} - {Month Year}` | `Ansible Meetup: London - October 2026` |

### 3.5 Constants

| Constant | Value | Purpose |
|---|---|---|
| `ORGANIZER_SLUG` | `ansible-meetups` | Pretix organizer path segment |
| `TEMPLATE_SLUG` | `ansible-meetup-template-v6` | Template event identifier |
| `CONTACT_EMAIL` | `ansible-community-events@redhat.com` | Organizer contact email |
| `DISCOURSE_PARENT_CATEGORY_ID` | `8` | Parent category for regional subcategories |
| `DISCOURSE_EVENTS_CATEGORY_ID` | `14` | Category for new event topics |

---

## 4. Core Workflows

### 4.1 Environment Reconciliation (`provision_environment.py`)

**Purpose:** Reconcile Pretix and Discourse resources to desired state. Resources are resolved by stable name, created if absent, and updated when security-relevant settings drift.

**Prerequisites:** `PRETIX_API_TOKEN` and `DISCOURSE_API_KEY` environment variables set.

**Phase 1: Discourse Provisioning**

0. Reconcile global staff group `meetup-staff` by stable name, creating it if absent and updating it if present. Set visibility level 4 (owners only).

For each city in the `CITIES` registry:

1. Reconcile organiser group `meetup-organisers-{slug}` by exact name; set visibility level 2 (members only) and update its description when it already exists.

2. Reconcile attendee group `meetup-attendee-{slug}` by exact name; force visibility level 3 (staff only).

3. Reconcile regional subcategory by parent and name, enforcing its description, color, permissions, and moderator assignment.

**Phase 2: Pretix Provisioning**

4. Configure organizer settings:
   - `PATCH /api/v1/organizers/ansible-meetups/`
   - Payload: `{"timezone": "UTC", "contact_mail": "ansible-community-events@redhat.com", "settings": {"organizer_team_creation": false}}`

5. Ensure `forum_topic_url` meta property exists:
   - `GET /api/v1/organizers/ansible-meetups/event_meta_properties/`
   - If no property named `forum_topic_url` in results:
     - `POST /api/v1/organizers/ansible-meetups/event_meta_properties/`
     - Payload: `{"name": "forum_topic_url", "default": "https://forum.ansible.com/c/events/8", "choices": []}`

6. Create or reconcile template event:
   - `GET /api/v1/organizers/ansible-meetups/events/ansible-meetup-template-v6/` (check existence via status code)
   - If 404:
     - `POST /api/v1/organizers/ansible-meetups/events/`
     - Payload: `{"name": {"en": "TEMPLATE: Standard Meetup"}, "slug": "ansible-meetup-template-v6", "live": false, "is_template": true, "currency": "USD", "date_from": "2026-12-31T18:00:00Z", "plugins": ["pretix.plugins.sendmail", "pretix.plugins.ticketoutputpdf"]}`
   - On every run, force `live=false`, `is_template=true`, and the desired plugin list.

7. Enforce template settings:
   - `PATCH /api/v1/organizers/ansible-meetups/events/ansible-meetup-template-v6/settings/`
   - Payload: See "Master Template Settings" in Section 3.3.

8. Ensure template has a default item + quota:
   - `GET /api/v1/organizers/ansible-meetups/events/ansible-meetup-template-v6/items/`
   - If no items:
     - `POST .../items/` → `{"name": {"en": "RSVP"}, "default_price": "0.00", "active": true, "admission": true}`
     - `POST .../quotas/` → `{"name": "Capacity", "size": 100, "items": [item_id]}`

9. Reconcile regional teams:
   - Fetch all teams using `pretix_list_all("teams")` (paginated).
   - For each city, create a missing team or update an existing team's `all_event_permissions`, `limit_event_permissions`, and scoped `limit_events` without widening access.

### 4.2 Event Creation (`create_event.py`)

**Purpose:** Provision a complete meetup: Discourse topic + Pretix event + social media copy. City input must be a registered lowercase ASCII slug.

**CLI Arguments:**

| Argument | Required | Type | Validation | Example |
|---|---|---|---|---|
| `--city` | Yes | string | `^[a-z]+$`; must resolve in `CITIES` | `london` |
| `--date` | Yes | string | Event local time, ISO-8601 parsed by `datetime.fromisoformat` | `2026-10-31T18:00:00` |
| `--capacity` | Yes | int | `argparse type=int` enforcement | `100` |
| `--organiser` | Yes | string | Discourse username; must be a member of the registered city's organiser group | `gundalow` |

**Derived Values:**

| Value | Derivation |
|---|---|
| `event_timezone` | Registered `get_city(city).timezone`; unknown city is rejected before API calls |
| `end_dt` | `dt + 3 hours` |
| `start_str` | `dt.strftime("%Y-%m-%dT%H:%M:%S")` (no Z suffix — local time) |
| `end_str` | `end_dt.strftime("%Y-%m-%dT%H:%M:%S")` (no Z suffix — local time) |
| `event_name` | `f"Ansible Meetup {city.title()}"` |
| `target_slug` | `f"{city.lower().replace(' ', '-')}-{mon}-{yyyy}"` (e.g., `manchester-oct-2026`) |

**Phase 0: Validation and Pre-flight**

- Reject city names outside `^[a-z]+$` and names absent from `CITIES` before API calls.
- Verify organiser, exact organiser-group membership, template, Pretix team, and API availability before mutations.
- `check_event_exists` returns `True`/`False` only for confirmed `200`/`404`; other statuses and network failures raise `ApiError`.
- Require HTTPS for `PRETIX_URL` except localhost and loopback development endpoints.

- Check if `target_slug` already exists in Pretix via `check_event_exists(target_slug)`.
- If it exists, **abort** (exit 1) with a clear error. API failures are not interpreted as absence.

**Phase 1: Create Discourse Topic**

- `POST /posts.json`
- Headers: `Api-Username: {organiser}` (impersonation)
- Payload: `{"title": "Ansible Meetup: {City} - {Month Year}", "raw": {initial_markdown}, "category": 14}`
- **MUST abort** (exit 1) if this fails. No Pretix event should be created without a forum topic.
- Extract `post_id`, `topic_slug`, and `topic_id` from response.
- Construct `forum_url = f"{DISCOURSE_URL}/t/{topic_slug}/{topic_id}"`

**Phase 2: Create Pretix Event**

- `POST /api/v1/organizers/ansible-meetups/events/`
- Payload: `{"name": {"en": event_name}, "slug": target_slug, "date_from": date, "date_to": end_date, "timezone": event_timezone, "clone_from": "ansible-meetup-template-v6", "meta_data": {"forum_topic_url": forum_url}}`
- **MUST abort** (exit 1) if this fails.
- If event creation fails after topic creation, attempt to delete the topic. If the result has no ID or cleanup fails, report that the operator must inspect and remove any orphan before retrying.
- Extract `final_slug` from response (may differ from `target_slug` if Pretix appends a suffix).
- Construct `pretix_public_url = f"{PRETIX_URL}/{ORGANIZER_SLUG}/{final_slug}/"`

**Phase 3: Update Discourse Post**

- Replace placeholder URL in event block: `url="https://link-pending.local"` → `url="{pretix_public_url}"`
- Replace RSVP placeholder: `*[RSVP link pending...]*` → `**[Click here to RSVP via Pretix]({pretix_public_url})**`
- `PUT /posts/{post_id}.json`
- Payload: `{"post": {"raw": final_markdown}}`
- Headers: `Api-Username: {organiser}` (impersonation)
- `ApiError` aborts the workflow; request failures do not become false success values.

**Phase 4: Sync to Pretix Frontpage**

- Split `final_markdown` on `---` (first occurrence). Take everything after the separator. Strip whitespace.
- If no `---` found, use the full markdown as fallback.
- `PATCH /api/v1/organizers/ansible-meetups/events/{slug}/settings/`
- Payload: `{"frontpage_text": {"en": pretix_content}}`

**Phase 5: Adjust Quota**

- `GET /api/v1/organizers/ansible-meetups/events/{slug}/quotas/`
- If quota exists (inherited from template): `PATCH .../quotas/{id}/` → `{"size": capacity}`
- If no quota:
  - `GET .../items/` to find existing items
  - If no items: create one (`POST .../items/` → `{"name": {"en": "RSVP"}, "default_price": "0.00", "active": true, "admission": true}`)
  - `POST .../quotas/` → `{"name": "Capacity", "size": capacity, "items": [item_id]}`

**Phase 6: Publish**

- `PATCH /api/v1/organizers/ansible-meetups/events/{slug}/` → `{"live": true}`

**Phase 7: Assign Team**

- Fetch all teams using `pretix_list_all("teams")` (paginated).
- Find team named `Ansible Meetup Organisers - {City}`.
- Fetch the full team by ID (`GET /api/v1/organizers/ansible-meetups/teams/{id}/`) to get the complete `limit_events` array (avoids pagination truncation from list endpoint).
- Append `final_slug` to `limit_events` list.
- `PATCH /api/v1/organizers/ansible-meetups/teams/{id}/` → `{"limit_events": [...], "all_event_permissions": false, "limit_event_permissions": ["event.orders:read", "event.orders:checkin"]}`

**Phase 8: Social Media Copy**

- Print to stdout (not file, not API).
- See Section 8 for full specification.

### 4.3 Content Sync (`pretix-sync-event.py`)

**Purpose:** One-way sync from Discourse (source of truth) to Pretix (frontpage display).

**CLI Arguments:**

| Argument | Required | Validation |
|---|---|---|
| `--slug` | Yes | `^[a-z0-9\-]+$` (lowercase alphanumerics and hyphens) |

**Steps:**

1. `GET /api/v1/organizers/ansible-meetups/events/{slug}/`
   - Validate response is a dict. Extract `meta_data.forum_topic_url`.
   - If missing, log error and abort.

2. Parse topic ID from URL using `urlparse`:
   - Extract path, strip slashes, split on `/`, take last segment.
   - Validate segment is numeric (`isdigit()`). Abort if not.

3. `GET /t/{topic_id}.json` (Discourse)
   - Extract `title` and the first post's ID from `post_stream.posts[0].id`.
   - Guard against empty posts list.

4. `GET /posts/{post_id}.json` (Discourse)
   - Extract `raw` field (original markdown of the first post).

5. Strip Discourse-only content:
   - Split raw markdown on `---` (first occurrence). Take everything after the separator. Strip whitespace.
   - If no `---` found, use the full markdown as fallback.

6. `PATCH /api/v1/organizers/ansible-meetups/events/{slug}/` → `{"name": {"en": title}}`

7. `PATCH /api/v1/organizers/ansible-meetups/events/{slug}/settings/` → `{"frontpage_text": {"en": pretix_content}}`

This now matches the behavior of `create_event.py` — both scripts strip the Discourse `[event]` BBCode block above the `---` separator and send only clean markdown to Pretix.

### 4.4 SSO Authentication (`discourse-connect-mvp.py`)

**Purpose:** Development/test toolkit for the DiscourseConnect SSO flow. NOT a production service.

**SSO Outbound Flow (`/login`):**

1. Generate cryptographic nonce: `secrets.token_urlsafe(32)`.
2. Store nonce in Flask session: `session["discourse_nonce"] = nonce`.
3. Build SSO URL:
   - Encode `{"nonce": nonce, "return_sso_url": CALLBACK_URL, "require_2fa": "true"}` unconditionally.
   - Base64-encode the URL-encoded string.
   - Sign with HMAC-SHA256 using `SSO_SECRET`.
   - URL-encode the Base64 payload.
   - Redirect user to `{DISCOURSE_BASE_URL}/session/sso_provider?sso={payload}&sig={signature}`.

**SSO Inbound Flow (`/callback`):**

1. Extract `sso` and `sig` from query parameters.
2. URL-decode `sso`, verify HMAC signature (constant-time comparison via `hmac.compare_digest`).
3. Base64-decode the payload, parse as URL-encoded key-value pairs.
4. **Nonce validation:**
   - Pop stored nonce from session.
   - If stored nonce is `None` (expired session) → reject with 403.
   - If `hmac.compare_digest(payload_nonce, stored_nonce)` fails → reject with 403.
5. Proceed to analysis.

**Analysis (Policy Engine):**

Enrichment:
- `GET /admin/users/{external_id}.json` → extract moderation status (`silenced_till`, `suspended_till`), staged status, trust level, and secondary groups.
- `GET /user-badges/{username}.json` → extract badge names.

Blocking rules (evaluated in order, all applicable reasons collected):

| Condition | Reason |
|---|---|
| `is_silenced(api)` — `silenced_till` present and non-null | `"moderation: silenced [until {date}]"` |
| `is_suspended(api)` — `suspended_till` present and non-null | `"moderation: suspended [until {date}]"` |
| `is_anonymised(data)` — `email.endswith("@anonymized.invalid")` | `"RTBF: anonymised (block future ticket purchase)"` |
| Privileged (`meetup-staff` or exact `meetup-organisers-[a-z]+`) without signed `confirmed_2fa=true` | `"privileged but DiscourseConnect did not confirm 2FA"` |

Permission levels (highest wins):

| Level | Condition |
|---|---|
| `blocked` | Any blocking reason triggered |
| `staff` | User is in the exact `meetup-staff` group |
| `organiser ({cities})` | User has exact `meetup-organisers-[a-z]+` groups |
| `regular` | Default |

**Status Check Functions:**

| Function | Check | Source |
|---|---|---|
| `is_anonymised(data)` | `email.endswith("@anonymized.invalid")` | SSO payload (email-domain only, matches Discourse `UserAnonymizer::EMAIL_SUFFIX`) |
| `is_silenced(api_data)` | `bool(api_data.get("silenced_till"))` | Admin API (`silenced_till` is a datetime, present only when silenced) |
| `is_suspended(api_data)` | `bool(api_data.get("suspended_till"))` | Admin API (`suspended_till` is a datetime, present only when suspended) |

**Note:** The Discourse Admin API does **not** return boolean `silenced` or `suspended` fields. It returns `silenced_till` and `suspended_till` as datetime values, **only when the user is silenced/suspended**. The helper functions check for presence and non-null value of these keys.

**Endpoints:**

| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Landing page with login link + last analysis result |
| `/login` | GET | Generate nonce, redirect to Discourse SSO |
| `/callback` | GET | Verify SSO payload, run analysis, display result |
| `/debug` | GET | JSON dump of last SSO state (HTML-escaped) |
| `/logout` | GET | Clear Flask session, redirect to `/` |

---

## 5. API Integration Contracts

### 5.1 Pretix API

**Base URL Construction:**

```
{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/{endpoint}
```

Trailing slash rules:
- If URL has no query string: ensure it ends with `/`.
- If URL has a query string: split on first `?`, ensure the base ends with `/`, rejoin.
- Never produce double slashes (except in `://`).

**Authentication:** `Authorization: Token {PRETIX_API_TOKEN}` header on every request.

**Content-Type:** `application/json` on every request.

**Timeout:** 10 seconds on all requests.

**Response Handling:**

| Status | Behavior |
|---|---|
| 200, 201, 204 | Success. Return JSON object, or `{}` for an empty body. |
| Any other | Raise `ApiError` with status and bounded response excerpt. |
| Connection error | Raise `ApiError`; never infer resource absence. |
| Invalid/non-object JSON | Raise `ApiError`. |

**Endpoints Used:**

| Method | Endpoint | Purpose |
|---|---|---|
| `PATCH` | *(empty — targets organizer)* | Update organizer settings |
| `GET` | `event_meta_properties` | List meta properties |
| `POST` | `event_meta_properties` | Create `forum_topic_url` property |
| `GET` | `events/{slug}` | Check event existence / fetch event |
| `POST` | `events` | Create event (or clone from template) |
| `PATCH` | `events/{slug}` | Update event (publish, set name) |
| `PATCH` | `events/{slug}/settings` | Update event settings (frontpage, checkout) |
| `GET` | `events/{slug}/items` | List ticket items |
| `POST` | `events/{slug}/items` | Create ticket item |
| `GET` | `events/{slug}/quotas` | List quotas |
| `POST` | `events/{slug}/quotas` | Create quota |
| `PATCH` | `events/{slug}/quotas/{id}` | Update quota size |
| `GET` | `teams` | List all teams (paginated via `pretix_list_all`) |
| `GET` | `teams/{id}` | Fetch single team (complete `limit_events` array) |
| `POST` | `teams` | Create team |
| `PATCH` | `teams/{id}` | Update team permissions/event limits |

### 5.2 Discourse API

**Base URL Construction:**

```
{DISCOURSE_URL.rstrip('/')}/{endpoint}
```

No trailing slash appended (Discourse endpoints include their own suffixes like `.json`).

**Authentication:** `Api-Key: {DISCOURSE_API_KEY}` + `Api-Username: {run_as or DISCOURSE_API_USER}` headers.

**Content-Type:** `application/json`.

**Timeout:** 10 seconds.

**Response Handling:**

Same typed contract as Pretix. Duplicate creation errors are not swallowed; provisioning first resolves resources by name and updates them.

**Endpoints Used:**

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `admin/groups.json` | Create Discourse group |
| `POST` | `categories.json` | Create regional subcategory |
| `POST` | `posts.json` | Create forum topic |
| `PUT` | `posts/{id}.json` | Update post content |
| `GET` | `posts/{id}.json` | Fetch single post raw markdown (for sync) |
| `GET` | `t/{topic_id}.json` | Fetch topic data (for post ID extraction) |

**SSO Toolkit Additional Endpoints (urllib, not httpx):**

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/admin/users/{external_id}.json` | Fetch moderation/status data; 2FA is asserted by signed DiscourseConnect response |
| `GET` | `/user-badges/{username}.json` | Fetch user badges |

---

## 6. Security Requirements

### Input Validation

| Input | Rule | Enforcement Point |
|---|---|---|
| `--city` | `^[a-z]+$`, registered in `CITIES` | Reject before API calls or mutations |
| `--slug` | `^[a-z0-9\-]+$` (lowercase alphanumerics, hyphens) | `pretix-sync-event.py` — return on mismatch |
| `--date` | Valid ISO-8601 | `datetime.fromisoformat()` — raises `ValueError` |
| `--capacity` | Integer | `argparse type=int` — rejects non-integers |
| `--organiser` | Discourse username | Membership-checked, then used as the Discourse `Api-Username` |
| Topic ID (from URL) | Numeric (`isdigit()`) | `pretix-sync-event.py` — return on mismatch |

### XSS Prevention

- All Jinja2 `render_template_string` output is auto-escaped by Flask.
- All non-Jinja2 HTML responses use `html.escape()`:
  - Error page status messages
  - `/debug` endpoint JSON dump

### SSO Security

- HMAC-SHA256 signature verification on all inbound payloads.
- Constant-time comparison via `hmac.compare_digest`.
- Nonce validation: stored nonce must be non-`None` AND must match payload nonce.
- Empty-nonce bypass prevented: `if not stored or not hmac.compare_digest(...)`.

### Log Sanitization

- API error response bodies truncated to 200 characters: `resp.text[:200]`.
- API tokens are in headers only, never in URLs or log messages.
- `httpx.HTTPError` exception messages do not include request headers.

### Attack and Misconfiguration Model

- A Pretix lookup returning an error or unknown status is never treated as proof that an event does not exist; the operation stops with `ApiError`.
- A city slug must match `^[a-z]+$` and be registered in `CITIES`. New cities must be added and deployed before event creation.
- The auth plugin trusts only `meetup-staff` and exact `^meetup-organisers-([a-z]+)$` group claims. Every claimed organiser group must resolve to a Pretix team or login is denied.
- Discourse groups are reconciled by name on every provisioning run. `meetup-staff` visibility is owners-only (level 4), organiser groups are members-only (level 2), and attendee groups are staff-only (level 3). Provisioning errors are fatal.
- Non-local `PRETIX_URL` values must use HTTPS so API tokens are not sent over cleartext HTTP.

### Known Accepted Risks

1. **Markdown relay:** `pretix-sync-event.py` copies raw Discourse markdown to Pretix. A malicious organizer could inject markdown that renders differently in Pretix than in Discourse. Mitigated by only trusted organizers having edit access to event topics.
2. **`run_as` scope:** `create_event.py --organiser` impersonates the selected Discourse user when posting. Membership is validated first; API key scope remains important.
3. **Flask secret key:** Default dev-only key is committed to source. Production deployment requires `FLASK_SECRET` env var override.
4. **`/debug` endpoint:** Exposes last user's full SSO profile. No authentication. Acceptable for localhost-only dev tool.

---

## 7. Forum Post Template

The forum post created by `create_event.py` has two distinct zones separated by a horizontal rule (`---`):

**Zone 1: Discourse-Only (NOT synced to Pretix)**

```markdown
[event start="{start_str}" end="{end_str}" timezone="{event_timezone}" minimal="true" name="{event_name}" url="https://link-pending.local"]
[/event]
```

- `minimal="true"`: Shows compact event widget without Interested/Attending buttons.
- No `status="public"`: Prevents RSVP buttons (RSVP is handled by Pretix).
- `url` is initially a placeholder; replaced with Pretix URL in Phase 3.

**Zone 2: Synced Content (written to Pretix frontpage)**

```markdown
## Welcome to Ansible Meetup {City}!

Join us for an evening of automation, collaboration, and community! ...

### What to Expect
- **Engaging Talks**: ...
- **Networking**: ...
- **Q&A**: ...
- **Community**: ...

### Location
**Venue details will be announced soon!** ...

### Agenda
* *Speaker 1: TBD*
* *Speaker 2: TBD*
*(Want to give a talk? Reply below with your proposal!)*

### RSVP
*[RSVP link pending...]*
**Please note:** To help us manage venue capacity ...

### Connect
Have questions? Want to propose a talk? ...
```

**Placeholder Replacements (Phase 3):**

| Placeholder | Replacement |
|---|---|
| `url="https://link-pending.local"` | `url="{pretix_public_url}"` |
| `*[RSVP link pending...]*` | `**[Click here to RSVP via Pretix]({pretix_public_url})**` |

**Sync to Pretix:**

`final_markdown.split("---", 1)[1].strip()` — takes everything after the first `---`, stripping whitespace. The `[event]` BBCode block is excluded because it does not render outside Discourse.

---

## 8. Social Media Copy Specification

Generated after successful event provisioning. Printed to stdout for manual copy-paste.

| Platform | Char Limit | Hashtags | Link Target | Fallback |
|---|---|---|---|---|
| **X / Twitter** | 280 | `#Ansible #Meetup #OpenSource` | Forum URL | Shorter text if over limit |
| **Bluesky** | 300 | `#Ansible #DevOps #Automation` | Forum URL | Shorter text if over limit |
| **Mastodon** | 500 | `#Ansible #Meetup #DevOps #Automation #OpenSource #InfrastructureAsCode` | Forum URL | None (always fits) |
| **LinkedIn** | None | `#Ansible #DevOps #Automation #InfrastructureAsCode #CommunityMeetup` | Forum URL | None |
| **Reddit** | None | None (markdown) | Forum URL | None |
| **Hacker News** | None | None | Forum URL | Title only, link on separate line |

All platforms link to the **forum URL**, not the Pretix URL. The forum is the community hub.

X and Bluesky include a fallback mechanism: if the primary text exceeds the character limit, a shorter version is used. Character count is printed after each payload.

---

## 9. Non-Functional Requirements

### HTTP

- **Timeout:** 10 seconds on ALL HTTP calls (httpx and urllib).
- **No retries:** Failed requests raise `ApiError`; CLI entry points report the error and exit non-zero.
- **No connection pooling:** Each `httpx.request()` call creates a new connection.

### Logging

- Python `logging` module, logger name `ansible_meetups`.
- Level: `INFO` by default.
- Format: `%(asctime)s - %(levelname)s - %(message)s`.
- Error responses: log at `ERROR` with status code + truncated body (200 chars max).
- Failures where script can continue: log at `WARNING`.

### Type Safety

- `from __future__ import annotations` in all files.
- Full type annotations on all function signatures (parameters + return types, including `-> None`).
- API wrappers return JSON objects and raise `ApiError` on failure; create/read operations require a JSON object response.
- Pyright with `typeCheckingMode = "standard"` (must pass with zero errors).
- Frozen slotted dataclasses for data models.

### Code Quality

- **Formatter:** ruff format (line-length 120).
- **Linter:** ruff check with rules: `E`, `F`, `B`, `S`, `T20`, `DTZ`, `UP`, `SIM`.
- **Import ordering:** isort with `--profile black`.
- **Per-file ignores:**
  - `create_event.py`: `T201` (print), `E501` (line length for social copy)
  - `discourse-connect-mvp.py`: `T201`, `S105` (hardcoded secret default), `S310` (urllib audit), `E501`
  - `main.py`: `T201`

### Testing

- **Framework:** pytest with `testpaths = ["tests"]`.
- **Organization:** Class-based (`Test<Feature>`), methods named `test_<verb>_<condition>`.
- **Coverage areas (43+ tests):**
  - `CityInfo.slug`: lowercase, spaces→hyphens, multiple spaces, empty, leading/trailing, tabs, unicode.
  - `CityInfo.field_value`: standard, multi-word, case preservation.
  - `CityInfo` frozen: immutability enforcement.
  - `get_city`: exact match, case-insensitive, not-found, partial match rejection, empty string, leading/trailing spaces.
  - `CITIES` registry: all CityInfo instances, no duplicates, valid timezones, tuple immutability.
  - Pretix URL building: trailing slashes, query strings, double slashes, empty endpoint.
  - Discourse URL building: slash stripping, nested paths.
  - `pre_flight_checks`: both vars set, missing discourse key, `require_discourse=False`.

### Dependencies

- **Runtime:** `httpx>=0.28`, `flask>=3.1.3`.
- **Dev:** `pytest>=8`, `pytest-cov>=6`, `ruff>=0.11`, `isort>=6`, `pyright>=1.1`.
- **Build:** Hatchling.
- **Package manager:** uv (with `uv.lock` committed).
- **Python:** `>=3.13`.

---

## 10. Checkout Experience Configuration

The Pretix checkout flow for authenticated attendees is:

1. User clicks RSVP link → Pretix redirects to Discourse SSO.
2. User authenticates on Discourse → redirect back to Pretix with signed payload.
3. SSO plugin pre-fills email from payload. Name pre-filled if available.
4. Checkout page shows: event name, single "Name" field (pre-filled, editable), RSVP button.
5. No email confirmation step, no payment step, no invoice address, no copy-answers button.
6. User submits → receives confirmation email with QR code and ICS calendar attachment.

**Name Behavior:**
- Pre-populated from Discourse SSO `name` field during login.
- User CAN edit their name during Pretix checkout.
- Edits are stored ONLY in Pretix. The Discourse profile is NEVER modified.
- Uses `name_scheme: "full"` — single text field, not given/family split.

**Settings enforced on template (all cloned events inherit):**

| Setting | Value | Effect |
|---|---|---|
| `max_items_per_order` | `1` | Prevents bulk RSVP |
| `invoice_address_asked` | `false` | No billing address form |
| `attendee_names_asked` | `true` | Name field visible at checkout |
| `attendee_names_required` | `true` | Name is mandatory |
| `attendee_emails_asked` | `false` | Email from SSO, not asked again |
| `name_scheme` | `"full"` | Single name field |
| `order_email_asked_twice` | `false` | No "confirm email" step |
| `payment_term_last` | `null` | No payment deadline |
| `checkout_show_copy_answers_button` | `false` | Irrelevant with 1-item orders |

---

## 11. Implicit Assumptions & Shortcuts

### No Retry or Backoff Logic

All API calls are fire-once. If a request fails due to a transient network error or rate limit, the operation fails. There is no exponential backoff, circuit breaker, or retry queue.

### Recovery after Partial Failure

`create_event.py` validates configuration and remote prerequisites before mutation. If Pretix event creation fails after the Discourse topic was created, it attempts to delete that topic. If cleanup fails, an operator must remove the orphan before retrying. Later API failures can still leave a partially configured event and must be resolved before announcing it.

The script aborts on API errors. Review the event and forum topic before announcing it; later mutations can leave partially configured resources that require operator repair.

### Partial Pagination

The `teams` list endpoint is paginated via `pretix_list_all`. Other list endpoints (`items`, `quotas`, `event_meta_properties`) still assume results fit in a single page (<50 results). At scale, these may need migration to `pretix_list_all`.

### Template Must Exist Before Event Creation

`create_event.py` uses `clone_from: ansible-meetup-template-v6`. It checks that the template exists before mutation. Run `provision_environment.py` to create or reconcile it.

### Single-Process Flask Dev Server

`discourse-connect-mvp.py` uses Flask's built-in server (`app.run(debug=False)`). The `_last` global dict stores the most recent SSO state across all requests. This is NOT safe for multi-user or production deployment.

### Hardcoded Cities Registry

The `CITIES` tuple is defined in source code. Adding a new city requires a code change, a lint pass, and re-deployment. There is no database, config file, or API for dynamic city management.

### Social Media Output

Social media copy is printed to stdout. There is no file output, clipboard integration, or API posting. The operator manually copies and pastes into each platform.

### No CI/CD Pipeline

There is no `.gitlab-ci.yml` or GitHub Actions workflow. Linting, testing, and type checking are manual (`bash lint.sh`, `uv run pytest`, `uv run pyright`).

### Event Duration Fixed at 3 Hours

`create_event.py` hardcodes `end_dt = dt + timedelta(hours=3)`. There is no CLI argument for event duration.

### Currency

All events use `"currency": "USD"` (inherited from the template). No per-city currency configuration exists. Since all events are free, this only affects display on confirmation emails.

---

## 12. Open Questions & Clarifications

### Q1: Partial Failure Compensation

The script attempts compensating cleanup if Pretix event creation fails. If the cleanup API call also fails, delete the topic manually before retrying. Unknown Pretix event state is fatal and never treated as absence.

### Q2: Scale & Pagination

**How many cities will this system support at maturity?** Teams listing is now paginated via `pretix_list_all`. Other list endpoints (`items`, `quotas`, `event_meta_properties`) still assume <50 results per page. If 50+ cities: consider async/concurrent provisioning in day0.

### Q3: SSO Toolkit Scope

Is `discourse-connect-mvp.py` a throwaway test tool, or should the rebuild include a production-grade SSO verification layer? If production: it needs proper session storage (Redis/DB), authentication on `/debug`, HTTPS enforcement, and WSGI deployment (gunicorn).

### Q4: Cities Registry Storage

Who adds new cities? Should the registry be:
- **Hardcoded** (current) — requires code deployment for each new city.
- **Config file** (YAML/JSON) — editable without code changes.
- **Discourse-driven** — auto-discover cities from existing `meetup-organisers-*` groups.
- **Database** — for API-managed CRUD.

### Q5: Event Duration

Event duration is hardcoded at 3 hours. **Should the rebuild accept a `--duration` CLI argument?** Most meetups are 2-3 hours, but unconferences or all-day workshops may need longer.

### Q6: `meetup-staff` Group Permissions

The `meetup-staff` group grants Pretix staff access. Only `meetup-staff` and exact `meetup-organisers-[a-z]+` groups are accepted by the auth plugin.

### Q7: Pretix API Rate Limits

What are the Pretix instance's API rate limits? `provision_environment.py` makes multiple API calls per city during reconciliation. At 50 cities, that's hundreds of sequential requests. **Do we need request throttling or backoff?** What about the Discourse API rate limits?
