from __future__ import annotations

import dataclasses
import logging
import os
import re
import sys
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("ansible_meetups")


class ApiError(RuntimeError):
    """An API request failed or returned an unexpected response."""


def run_cli(action: Callable[[], None]) -> None:
    """Run a CLI action and translate API failures into one friendly error."""
    try:
        action()
    except ApiError as exc:
        logger.error("API request failed: %s", exc)
        raise SystemExit(1) from exc


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

# --- Naming ---
EVENT_NAME_PREFIX = "Ansible Meetup"
ORGANISER_TEAM_PREFIX = "Ansible Meetup Organisers"
ORGANISERS_GROUP_PREFIX = "meetup-organisers"
ATTENDEE_GROUP_PREFIX = "meetup-attendee"
STAFF_TEAM_NAME = "Ansible Meetup Staff"
GROUP_VISIBILITY_OWNERS_ONLY = 4
GROUP_VISIBILITY_STAFF_ONLY = 3
MIGRATED_GROUP_NAME = "meetup-migrated-from-meetup-pro"
CITY_SLUG_RE = re.compile(r"^[a-z]+$")
ORGANIZERS_GROUP_RE = re.compile(r"^meetup-organisers-([a-z]+)$")
MONTH_SLUGS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
EVENT_SLUG_RE = re.compile(rf"^([a-z]+)-({'|'.join(MONTH_SLUGS)})-[0-9]{{4}}$")
API_REQUEST_TIMEOUT_SECONDS = 10

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
    slug: str
    city: str
    timezone: str

    def __post_init__(self) -> None:
        if not CITY_SLUG_RE.fullmatch(self.slug):
            raise ValueError(f"City slug must contain lowercase ASCII letters only: {self.slug!r}")
        if not self.city.strip() or not self.region.strip() or not self.country.strip():
            raise ValueError("City display name, region, and country must not be empty")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Invalid IANA timezone: {self.timezone!r}") from exc

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
    def organiser_group(self) -> str:
        return f"{ORGANISERS_GROUP_PREFIX}-{self.slug}"

    @property
    def attendee_group(self) -> str:
        return f"{ATTENDEE_GROUP_PREFIX}-{self.slug}"


CITIES: tuple[CityInfo, ...] = (
    CityInfo(region="Europe", country="UK", slug="london", city="London", timezone="Europe/London"),
    CityInfo(region="Europe", country="Spain", slug="barcelona", city="Barcelona", timezone="Europe/Madrid"),
    CityInfo(region="Europe", country="UK", slug="faketown", city="FakeTown", timezone="Europe/London"),
)

if len({city.slug for city in CITIES}) != len(CITIES):
    raise ValueError("City slugs in CITIES must be unique")
if len({city.city.casefold() for city in CITIES}) != len(CITIES):
    raise ValueError("City display names in CITIES must be unique")


def get_city(name: str) -> CityInfo | None:
    """Look up a registered city slug. Returns None for malformed or unknown names."""
    if not CITY_SLUG_RE.fullmatch(name):
        return None
    for c in CITIES:
        if c.slug == name:
            return c
    return None


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
    return any(g.get("name") == group_name for g in groups)


def discourse_city_category_id(city_name: str) -> int:
    """Resolve the registered city's Events subcategory, failing on missing or ambiguous state."""
    response = discourse_req("GET", "categories.json")
    category_list = response.get("category_list")
    if not isinstance(category_list, dict):
        raise ApiError("Discourse categories response is missing category_list")
    roots = category_list.get("categories")
    if not isinstance(roots, list):
        raise ApiError("Discourse categories response is missing categories")

    categories: list[dict[str, Any]] = []

    def flatten(rows: list[Any]) -> None:
        for row in rows:
            if not isinstance(row, dict):
                raise ApiError("Discourse categories response contains an invalid category")
            categories.append(row)
            children = row.get("subcategory_list", row.get("subcategories", []))
            if children is not None:
                if not isinstance(children, list):
                    raise ApiError("Discourse categories response contains invalid subcategories")
                flatten(children)

    flatten(roots)
    matches = [
        category
        for category in categories
        if category.get("name", "").casefold() == city_name.casefold()
        and category.get("parent_category_id") == DISCOURSE_PARENT_CATEGORY_ID
    ]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), int):
        raise ApiError(f"Expected exactly one Events subcategory for {city_name!r}; found {len(matches)}")
    return matches[0]["id"]


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
    parsed = urlparse(PRETIX_URL)
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        logger.error("PRETIX_URL must use HTTPS outside localhost/loopback")
        missing.append("secure PRETIX_URL")
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)


def pretix_req(method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Make an authenticated Pretix API request.

    Returns parsed JSON on success. Raises ApiError on every failure.
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
        resp = httpx.request(method, url, json=payload, headers=headers, timeout=API_REQUEST_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ApiError(f"Pretix {method} {endpoint} connection error: {exc}") from exc
    if resp.status_code not in (200, 201, 204):
        raise ApiError(f"Pretix {method} {endpoint} failed: {resp.status_code} {resp.text[:200]}")
    if not resp.text:
        if method.upper() in {"GET", "POST"}:
            raise ApiError(f"Pretix {method} {endpoint} returned an empty response body")
        return {}
    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiError(f"Pretix {method} {endpoint} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(f"Pretix {method} {endpoint} returned non-object JSON")
    return data


def discourse_req(
    method: str,
    endpoint: str,
    payload: dict[str, Any] | None = None,
    *,
    run_as: str | None = None,
    empty_response: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make an authenticated Discourse API request.

    Args:
        run_as: Override the API username for this request (e.g. to post
            on behalf of a specific user).
        empty_response: Response object to use for an expected bodyless 204.

    Returns parsed JSON on success. Raises ApiError on every failure.
    """
    url = f"{DISCOURSE_URL.rstrip('/')}/{endpoint}"
    headers = {
        "Api-Key": DISCOURSE_API_KEY,
        "Api-Username": run_as or DISCOURSE_API_USER,
        "Content-Type": "application/json",
    }
    try:
        resp = httpx.request(method, url, json=payload, headers=headers, timeout=API_REQUEST_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ApiError(f"Discourse {method} {endpoint} connection error: {exc}") from exc
    if resp.status_code not in (200, 201, 204):
        raise ApiError(f"Discourse {method} {endpoint} failed: {resp.status_code} {resp.text[:200]}")
    if not resp.text:
        if method.upper() in {"GET", "POST"}:
            if resp.status_code == 204 and empty_response is not None:
                return empty_response
            raise ApiError(f"Discourse {method} {endpoint} returned an empty response body")
        return {}
    try:
        data = resp.json()
    except ValueError as exc:
        raise ApiError(f"Discourse {method} {endpoint} returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise ApiError(f"Discourse {method} {endpoint} returned non-object JSON")
    return data


def pretix_list_all(endpoint: str) -> list[dict[str, Any]]:
    """Fetch all results from a paginated Pretix list endpoint."""
    results: list[dict[str, Any]] = []
    resp = pretix_req("GET", endpoint)
    configured_url = urlparse(PRETIX_URL)
    api_base = urljoin(
        f"{PRETIX_URL.rstrip('/')}/",
        f"api/v1/organizers/{ORGANIZER_SLUG}/",
    )
    expected_path_prefix = f"{configured_url.path.rstrip('/')}/api/v1/organizers/{ORGANIZER_SLUG}/"

    def checked_next_url(next_url: str) -> str:
        resolved = urlparse(urljoin(api_base, next_url))
        try:
            configured_port = configured_url.port or (443 if configured_url.scheme == "https" else 80)
            resolved_port = resolved.port or (443 if resolved.scheme == "https" else 80)
        except ValueError as exc:
            raise ApiError("Pretix pagination returned an invalid URL") from exc
        if (
            resolved.scheme != configured_url.scheme
            or resolved.hostname != configured_url.hostname
            or resolved_port != configured_port
            or resolved.username is not None
            or resolved.password is not None
            or not resolved.path.startswith(expected_path_prefix)
        ):
            raise ApiError("Pretix pagination URL is outside the configured organizer API")
        return resolved.geturl()

    while True:
        batch = resp.get("results")
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise ApiError("Pretix list response contains invalid results")
        results.extend(batch)
        next_url = resp.get("next")
        if next_url is None:
            break
        if not isinstance(next_url, str) or not next_url:
            raise ApiError("Pretix pagination returned an invalid next URL")
        page_url = checked_next_url(next_url)
        try:
            page_resp = httpx.get(
                page_url,
                headers={"Authorization": f"Token {PRETIX_API_TOKEN}", "Content-Type": "application/json"},
                timeout=API_REQUEST_TIMEOUT_SECONDS,
            )
            if page_resp.status_code != 200:
                raise ApiError(f"Pretix pagination failed: {page_resp.status_code}")
            resp = page_resp.json()
            if not isinstance(resp, dict):
                raise ApiError("Pretix pagination returned non-object JSON")
        except (httpx.HTTPError, ValueError) as exc:
            raise ApiError("Pretix pagination request failed") from exc
    return results


def check_event_exists(slug: str) -> bool:
    """Return True/False for a confirmed event/404; raise ApiError otherwise."""
    url = f"{PRETIX_URL}/api/v1/organizers/{ORGANIZER_SLUG}/events/{slug}/"
    headers = {"Authorization": f"Token {PRETIX_API_TOKEN}"}
    try:
        resp = httpx.get(url, headers=headers, timeout=API_REQUEST_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ApiError(f"Pretix check_event_exists {slug} connection error: {exc}") from exc
    if resp.status_code == 404:
        return False
    if resp.status_code == 200:
        return True
    raise ApiError(f"Pretix check_event_exists {slug} failed: {resp.status_code} {resp.text[:200]}")


def strip_discourse_block(markdown: str) -> str:
    """Strip Discourse-only content above the first --- separator."""
    return markdown.split("---", 1)[1].strip() if "---" in markdown else markdown
