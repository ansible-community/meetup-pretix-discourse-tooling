#!/usr/bin/env python3
"""Reconcile Discourse groups/categories and Pretix template/teams to desired state.

Safe to run repeatedly. Designed for both initial setup and ongoing maintenance
as new cities are added to the CITIES registry.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ansible_events_lib import (
    ANSIBLE_PRIMARY_COLOR,
    ApiError,
    ATTENDEE_GROUP_PREFIX,
    EVENT_SLUG_RE,
    CITIES,
    CODE_OF_CONDUCT_URL,
    CONTACT_EMAIL,
    DEFAULT_ITEM_NAME,
    DEFAULT_ITEM_PRICE,
    DEFAULT_QUOTA_NAME,
    DISCOURSE_PARENT_CATEGORY_ID,
    EVENTS_FORUM_URL,
    MIGRATED_GROUP_NAME,
    ORGANISERS_GROUP_PREFIX,
    ORGANISER_PERMISSIONS,
    STAFF_TEAM_NAME,
    GROUP_VISIBILITY_OWNERS_ONLY,
    GROUP_VISIBILITY_STAFF_ONLY,
    PRIVACY_POLICY_URL,
    TEMPLATE_SLUG,
    USER_CITY_FIELD_ID,
    check_event_exists,
    discourse_req,
    discourse_city_category_id,
    logger,
    pre_flight_checks,
    pretix_list_all,
    pretix_req,
    run_cli,
)


def list_discourse_groups() -> list[dict]:
    """Fetch every Discourse group page so reconciliations cannot miss later groups."""
    groups: list[dict] = []
    page = 0
    while True:
        response = discourse_req("GET", f"admin/groups.json?page={page}", empty_response={"groups": []})
        batch = response.get("groups")
        if not isinstance(batch, list):
            raise ApiError("Discourse groups response is missing groups")
        if any(not isinstance(group, dict) for group in batch):
            raise ApiError("Discourse groups response contains an invalid group")
        groups.extend(batch)
        if not batch:
            return groups
        page += 1


GROUP_RECONCILE_FIELDS = (
    "name",
    "full_name",
    "bio_raw",
    "visibility_level",
    "members_visibility_level",
    "public_admission",
    "allow_membership_requests",
    "automatic_membership_email_domains",
)

FIELD_LABELS: dict[str, str] = {
    "full_name": "full name",
    "bio_raw": "description",
    "visibility_level": "visibility",
    "members_visibility_level": "member visibility",
    "public_admission": "public admission",
    "allow_membership_requests": "membership requests",
    "automatic_membership_email_domains": "automatic membership domains",
    "owner_usernames": "group owners",
    "permissions": "permissions",
    "moderating_group_ids": "moderator groups",
    "tracking_category_ids": "tracking categories",
    "all_events": "all events",
    "all_event_permissions": "all event permissions",
    "limit_event_permissions": "event permissions",
    "all_organizer_permissions": "all organizer permissions",
    "limit_organizer_permissions": "organizer permissions",
    "limit_events": "event scope",
}
UNORDERED_FIELDS: set[str] = {
    "limit_event_permissions",
    "limit_organizer_permissions",
    "limit_events",
    "moderating_group_ids",
    "tracking_category_ids",
}


def same_configuration_value(field: str, current: Any, desired: Any) -> bool:
    if field in UNORDERED_FIELDS and isinstance(current, list) and isinstance(desired, list):
        return set(current) == set(desired)
    return current == desired


def log_resource_status(
    resource: str,
    desired: Mapping[str, Any],
    before: Mapping[str, Any] | None,
    extra_status: Mapping[str, str] | None = None,
) -> None:
    """Log whether each desired field was already correct or had to change."""
    statuses = {
        FIELD_LABELS.get(field, field.replace("_", " ")): (
            "OK" if before is None or same_configuration_value(field, before.get(field), value) else "Changed"
        )
        for field, value in desired.items()
    }
    statuses.update(extra_status or {})
    if before is None:
        state = "Created"
    elif any(status == "Changed" for status in statuses.values()):
        state = "Updated"
    else:
        state = "Already configured"
    details = ", ".join(f"{field}: {status}" for field, status in statuses.items())
    logger.info("%s: %s | %s", resource, state, details)


def ensure_discourse_groups(city_slug: str, city_name: str) -> tuple[str, str, int]:
    host_group = f"{ORGANISERS_GROUP_PREFIX}-{city_slug}"
    attendee_group = f"{ATTENDEE_GROUP_PREFIX}-{city_slug}"

    def ensure_group(name: str, group: dict) -> int:
        groups = list_discourse_groups()
        matches = [item for item in groups if item.get("name") == name]
        if len(matches) > 1:
            raise ApiError(f"Multiple Discourse groups are named {name!r}")
        existing = matches[0] if matches else None
        payload = {"group": group}
        before = None
        before_owners = []
        if existing:
            details = discourse_req("GET", f"groups/by-id/{existing['id']}.json")
            before = details.get("group")
            if not isinstance(before, dict):
                raise ApiError(f"Could not read current settings for Discourse group {name!r}")
            owners_response = discourse_req("GET", f"groups/{name}/members.json")
            before_owners = owners_response.get("owners")
            if not isinstance(before_owners, list):
                raise ApiError(f"Could not read owners for Discourse group {name!r}")
            changed = any(
                not same_configuration_value(key, before.get(key), value)
                for key, value in group.items()
                if key in GROUP_RECONCILE_FIELDS
            )
            if changed or before_owners:
                discourse_req("PUT", f"groups/{existing['id']}.json", payload)
            group_id = existing.get("id")
        else:
            created = discourse_req("POST", "admin/groups.json", payload)
            group_id = created.get("basic_group", created).get("id")
            groups = list_discourse_groups()
            created = next((item for item in groups if item.get("name") == name), None)
            if created:
                group_id = created.get("id")
        if not isinstance(group_id, int):
            raise ApiError(f"Could not resolve Discourse group ID for {name!r}")
        response = discourse_req("GET", f"groups/by-id/{group_id}.json")
        actual = response.get("group")
        if actual is None or any(actual.get(key) != group[key] for key in GROUP_RECONCILE_FIELDS if key in group):
            raise ApiError(f"Discourse group {name!r} did not reconcile to the requested settings")
        if name.startswith(f"{ORGANISERS_GROUP_PREFIX}-"):
            members_response = discourse_req("GET", f"groups/{name}/members.json")
            owners = members_response.get("owners")
            if not isinstance(owners, list) or owners:
                raise ApiError(f"Discourse organiser group {name!r} must have no group owners")
            log_resource_status(
                name,
                {key: value for key, value in group.items() if key in GROUP_RECONCILE_FIELDS},
                before,
                {"group owners": "Changed" if before_owners else "OK"},
            )
        else:
            log_resource_status(
                name,
                {key: value for key, value in group.items() if key in GROUP_RECONCILE_FIELDS},
                before,
            )
        return group_id

    host_group_id = ensure_group(
        host_group,
        {
            "name": host_group,
            "full_name": f"Ansible Meetup Organisers - {city_name}",
            "bio_raw": (
                f"Organisers for Ansible Community Meetups in {city_name}.\n\n"
                "**Requirements:** Members must have 2FA enabled on their forum account "
                "and be approved by the Community Engineering lead.\n\n"
                "This group grants Category Moderator rights on the "
                f"{city_name} Events subcategory and scoped access to the "
                "Pretix event dashboard (attendee list + check-in)."
            ),
            "visibility_level": GROUP_VISIBILITY_OWNERS_ONLY,
            "members_visibility_level": GROUP_VISIBILITY_OWNERS_ONLY,
            "public_admission": False,
            "allow_membership_requests": False,
            "automatic_membership_email_domains": "",
            "owner_usernames": "",
        },
    )
    ensure_group(
        attendee_group,
        {
            "name": attendee_group,
            "full_name": f"Ansible Meetup Attendees - {city_name}",
            "bio_raw": (
                f"Notification subscription group for Ansible Meetup events in {city_name}.\n\n"
                "Members receive notifications when new events are posted. "
                "Membership is hidden (visible to forum admins only) to protect location privacy."
            ),
            "visibility_level": GROUP_VISIBILITY_STAFF_ONLY,
            "members_visibility_level": GROUP_VISIBILITY_STAFF_ONLY,
        },
    )
    return host_group, attendee_group, host_group_id


def ensure_group_tracks_city_category(group_name: str, group_id: int, category_id: int) -> None:
    """Set the organiser group's default notification level to Tracking for its city category."""
    before_response = discourse_req("GET", f"groups/by-id/{group_id}.json")
    before = before_response.get("group")
    if not isinstance(before, dict):
        raise ApiError(f"Could not read current settings for Discourse group {group_name!r}")
    current_ids = before.get("tracking_category_ids", [])
    if not isinstance(current_ids, list) or any(not isinstance(value, int) for value in current_ids):
        raise ApiError(f"Discourse group {group_name!r} returned invalid tracking category IDs")

    desired = {"tracking_category_ids": [category_id]}
    if not same_configuration_value("tracking_category_ids", current_ids, desired["tracking_category_ids"]):
        discourse_req(
            "PUT",
            f"groups/{group_id}.json",
            {"group": desired, "update_existing_users": "true"},
        )

    after_response = discourse_req("GET", f"groups/by-id/{group_id}.json")
    after = after_response.get("group")
    if not isinstance(after, dict) or not same_configuration_value(
        "tracking_category_ids", after.get("tracking_category_ids"), desired["tracking_category_ids"]
    ):
        raise ApiError(f"Discourse group {group_name!r} failed category notification reconciliation")
    log_resource_status(f"{group_name} category notifications", desired, before)


def ensure_discourse_category(city_name: str, host_group: str, attendee_group: str, host_group_id: int) -> None:
    desired = {
        "name": city_name,
        "parent_category_id": DISCOURSE_PARENT_CATEGORY_ID,
        "color": "EE0000",
        "text_color": "FFFFFF",
        "description": (
            f"Ansible Community Meetup events in {city_name}. "
            f"Free, in-person meetups for automation enthusiasts — "
            f"talks, networking, and community. "
            f"RSVP to upcoming Ansible Meetup {city_name} events below."
        ),
        "permissions": {"everyone": 1, host_group: 1, attendee_group: 1},
        "moderating_group_ids": [host_group_id],
    }
    categories = discourse_req("GET", "categories.json").get("category_list", {}).get("categories", [])

    def flatten(rows: list[dict]) -> list[dict]:
        result = []
        for row in rows:
            result.append(row)
            result.extend(flatten(row.get("subcategory_list", row.get("subcategories", []))))
        return result

    categories = flatten(categories)
    matching_categories = [
        category
        for category in categories
        if category.get("name", "").lower() == city_name.lower()
        and category.get("parent_category_id") == DISCOURSE_PARENT_CATEGORY_ID
    ]
    if len(matching_categories) > 1:
        raise ApiError(f"Multiple Discourse city categories are named {city_name!r}")
    existing = matching_categories[0] if matching_categories else None
    before = None
    if existing:
        before_response = discourse_req("GET", f"categories/{existing['id']}.json")
        before = before_response.get("category", before_response)
        if not isinstance(before, dict):
            raise ApiError(f"Could not read current settings for Discourse category {city_name!r}")
        if any(not same_configuration_value(key, before.get(key), value) for key, value in desired.items()):
            discourse_req("PUT", f"categories/{existing['id']}.json", desired)
    else:
        discourse_req("POST", "categories.json", desired)
    category_id = discourse_city_category_id(city_name)
    result = discourse_req("GET", f"categories/{category_id}.json")
    category = result.get("category", result)
    if any(not same_configuration_value(key, category.get(key), value) for key, value in desired.items()):
        raise ApiError(f"Discourse category {city_name!r} did not reconcile to city-only access")
    log_resource_status(
        f"Events > {city_name}",
        desired,
        before,
    )


def reconcile_organiser_category_access(
    city_access: dict[int, tuple[str, int]],
) -> None:
    """Keep each organiser group on its own city category only."""
    category_list = discourse_req("GET", "categories.json").get("category_list", {})
    roots = category_list.get("categories") if isinstance(category_list, dict) else None
    if not isinstance(roots, list):
        raise ApiError("Discourse categories response is missing categories")

    categories: list[dict] = []

    def flatten(rows: list) -> None:
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
    group_rows = list_discourse_groups()
    managed_group_ids = {group_id for _, group_id in city_access.values()}
    for group in group_rows:
        if not isinstance(group, dict):
            raise ApiError("Discourse groups response contains an invalid group")
        group_name = group.get("name")
        if isinstance(group_name, str) and group_name.startswith(f"{ORGANISERS_GROUP_PREFIX}-"):
            group_id = group.get("id")
            if not isinstance(group_id, int):
                raise ApiError("Discourse organiser group response contains an invalid ID")
            managed_group_ids.add(group_id)

    for category in categories:
        category_id = category.get("id")
        if not isinstance(category_id, int):
            raise ApiError("Discourse categories response contains an invalid category ID")
        detail = discourse_req("GET", f"categories/{category_id}.json")
        detail = detail.get("category", detail)
        current_ids = detail.get("moderating_group_ids") if isinstance(detail, dict) else None
        if not isinstance(current_ids, list) or any(not isinstance(group_id, int) for group_id in current_ids):
            raise ApiError(f"Discourse category {category_id} returned invalid moderator group IDs")

        desired_ids = [group_id for group_id in current_ids if group_id not in managed_group_ids]
        city_access_for_category = city_access.get(category_id)
        if city_access_for_category is not None:
            _, city_group_id = city_access_for_category
            desired_ids.append(city_group_id)
        desired_ids = sorted(set(desired_ids))
        if desired_ids != sorted(set(current_ids)):
            discourse_req(
                "PUT",
                f"categories/{category_id}.json",
                {"moderating_group_ids": desired_ids},
            )

        permissions = detail.get("permissions") if isinstance(detail, dict) else None
        if not isinstance(permissions, dict):
            raise ApiError(f"Discourse category {category_id} returned invalid permissions")
        desired_permissions = {
            name: level
            for name, level in permissions.items()
            if not (isinstance(name, str) and name.startswith(f"{ORGANISERS_GROUP_PREFIX}-"))
        }
        if city_access_for_category is not None:
            city_group_name, _ = city_access_for_category
            desired_permissions[city_group_name] = 1
        if desired_permissions != permissions:
            discourse_req(
                "PUT",
                f"categories/{category_id}.json",
                {"permissions": desired_permissions},
            )

        if desired_ids != sorted(set(current_ids)) or desired_permissions != permissions:
            updated = discourse_req("GET", f"categories/{category_id}.json")
            updated = updated.get("category", updated)
            updated_ids = updated.get("moderating_group_ids")
            updated_permissions = updated.get("permissions")
            if (
                not isinstance(updated_ids, list)
                or sorted(set(updated_ids)) != desired_ids
                or updated_permissions != desired_permissions
            ):
                raise ApiError(f"Discourse category {category_id} failed access reconciliation")
        logger.info(
            "Discourse category %s (%s): moderator groups: %s, organiser permissions: %s",
            detail.get("name", category_id),
            category_id,
            "Changed" if desired_ids != sorted(set(current_ids)) else "OK",
            "Changed" if desired_permissions != permissions else "OK",
        )


def ensure_category_group_moderation_enabled() -> None:
    """Fail unless Discourse permits assigning groups as category moderators."""
    response = discourse_req(
        "GET",
        "admin/site_settings.json?names%5B%5D=enable_category_group_moderation",
    )
    settings = response.get("site_settings")
    if not isinstance(settings, list):
        raise ApiError("Could not verify Discourse category group moderation setting")
    setting = next(
        (item for item in settings if item.get("setting") == "enable_category_group_moderation"),
        None,
    )
    if not setting or str(setting.get("value")).lower() != "true":
        raise ApiError("Discourse enable_category_group_moderation must be enabled to assign city organisers")


def ensure_user_field_options() -> None:
    """Add any missing city options to the user_event_cities custom field (additive only)."""
    logger.info("Syncing user field options for city subscriptions...")

    # GET uses hyphenated path, PUT uses underscored path (Discourse routing)
    resp = discourse_req("GET", f"admin/config/user-fields/{USER_CITY_FIELD_ID}.json")
    if not resp:
        raise RuntimeError(f"Could not fetch user field {USER_CITY_FIELD_ID}")

    current_options = set(resp.get("user_field", {}).get("options", []))
    desired_options = {city.field_value for city in CITIES}
    missing = desired_options - current_options

    if not missing:
        logger.info("User field options up to date (%d options)", len(current_options))
        return

    updated_options = sorted(current_options | desired_options)
    logger.info("Adding %d new option(s): %s", len(missing), ", ".join(sorted(missing)))

    discourse_req(
        "PUT",
        f"admin/config/user_fields/{USER_CITY_FIELD_ID}.json",
        {"user_field": {"options": updated_options}},
    )


def main() -> None:
    pre_flight_checks()

    logger.info("--- 1. PRETIX PROVISIONING ---")
    pretix_req(
        "PATCH",
        "",
        {
            "timezone": "UTC",
            "contact_mail": CONTACT_EMAIL,
            "settings": {"organizer_team_creation": False},
        },
    )
    logger.info("Configuring branding, footer links, and legal URLs...")
    pretix_req(
        "PATCH",
        "settings",
        {
            "primary_color": ANSIBLE_PRIMARY_COLOR,
            "imprint_url": {"en": CODE_OF_CONDUCT_URL},
            "privacy_url": {"en": PRIVACY_POLICY_URL},
            "organizer_homepage_text": {
                "en": (
                    "Welcome to Ansible Community Meetups! "
                    f"Browse upcoming events and RSVP, or visit [the forum]({EVENTS_FORUM_URL}) "
                    "for discussions, talk proposals, and community."
                )
            },
        },
    )

    logger.info("Reconciling Pretix staff team %s...", STAFF_TEAM_NAME)
    staff_teams = [team for team in pretix_list_all("teams") if team.get("name") == STAFF_TEAM_NAME]
    if len(staff_teams) > 1:
        raise ApiError(f"Multiple Pretix teams are named {STAFF_TEAM_NAME!r}")
    staff_team_payload = {
        "name": STAFF_TEAM_NAME,
        "all_events": True,
        "limit_events": [],
        "all_event_permissions": True,
        "limit_event_permissions": [],
        "all_organizer_permissions": False,
        "limit_organizer_permissions": [],
    }
    previous_staff_team = staff_teams[0] if staff_teams else None
    if staff_teams:
        if any(
            not same_configuration_value(key, staff_teams[0].get(key), value)
            for key, value in staff_team_payload.items()
        ):
            pretix_req("PATCH", f"teams/{staff_teams[0]['id']}", staff_team_payload)
        staff_team = pretix_req("GET", f"teams/{staff_teams[0]['id']}")
    else:
        created_staff_team = pretix_req("POST", "teams", staff_team_payload)
        staff_team_id = created_staff_team.get("id")
        if not isinstance(staff_team_id, int):
            raise ApiError(f"Could not resolve Pretix staff team {STAFF_TEAM_NAME!r}")
        staff_team = pretix_req("GET", f"teams/{staff_team_id}")
    if (
        any(staff_team.get(key) != value for key, value in staff_team_payload.items() if key != "name")
        or staff_team.get("name") != STAFF_TEAM_NAME
    ):
        raise ApiError(f"Pretix staff team {STAFF_TEAM_NAME!r} did not reconcile to the requested settings")
    log_resource_status(STAFF_TEAM_NAME, staff_team_payload, previous_staff_team)

    logger.info("Reconciling regional Pretix Teams...")
    all_teams = pretix_list_all("teams")
    all_events = pretix_list_all("events")
    teams_by_name: dict[str, list[dict]] = {}
    for team in all_teams:
        name = team.get("name")
        if not isinstance(name, str):
            raise ApiError("Pretix teams response contains a team without a valid name")
        teams_by_name.setdefault(name, []).append(team)
    for city in CITIES:
        if any(
            isinstance(event.get("slug"), str)
            and event["slug"].startswith(f"{city.slug}-")
            and not EVENT_SLUG_RE.fullmatch(event["slug"])
            for event in all_events
        ):
            raise ApiError(f"Pretix has an invalid event slug for registered city {city.slug!r}")
        city_events = sorted(
            event["slug"]
            for event in all_events
            if isinstance(event.get("slug"), str)
            and (match := EVENT_SLUG_RE.fullmatch(event["slug"]))
            and match.group(1) == city.slug
        )
        desired_team = {
            "name": city.team_name,
            "all_events": False,
            "all_event_permissions": False,
            "limit_event_permissions": ORGANISER_PERMISSIONS,
            "all_organizer_permissions": False,
            "limit_organizer_permissions": [],
            "limit_events": city_events,
        }
        existing = teams_by_name.get(city.team_name, [])
        if len(existing) > 1:
            raise ApiError(f"Multiple Pretix teams are named {city.team_name!r}")
        previous_team = existing[0] if existing else None
        if existing:
            team_id = existing[0].get("id")
            if not isinstance(team_id, int):
                raise ApiError(f"Pretix team {city.team_name!r} has an invalid ID")
            if any(
                not same_configuration_value(field, existing[0].get(field), value)
                for field, value in desired_team.items()
            ):
                pretix_req("PATCH", f"teams/{team_id}", desired_team)
        else:
            created_team = pretix_req(
                "POST",
                "teams",
                desired_team,
            )
            team_id = created_team.get("id")
            if not isinstance(team_id, int):
                raise ApiError(f"Could not resolve Pretix team {city.team_name!r}")
        actual_team = pretix_req("GET", f"teams/{team_id}")
        for field in (
            "all_events",
            "all_event_permissions",
            "all_organizer_permissions",
        ):
            if actual_team.get(field) != desired_team[field]:
                raise ApiError(f"Pretix team {city.team_name!r} did not reconcile field {field!r}")
        for field in (
            "limit_event_permissions",
            "limit_organizer_permissions",
            "limit_events",
        ):
            actual_values = actual_team.get(field)
            if not isinstance(actual_values, list) or set(actual_values) != set(desired_team[field]):
                raise ApiError(f"Pretix team {city.team_name!r} did not reconcile field {field!r}")
        log_resource_status(city.team_name, desired_team, previous_team)

    props_resp = pretix_req("GET", "event_meta_properties")
    if props_resp:
        props = props_resp.get("results", [])
        if not any(p["name"] == "forum_topic_url" for p in props):
            pretix_req(
                "POST",
                "event_meta_properties",
                {
                    "name": "forum_topic_url",
                    "default": "https://forum.ansible.com/c/events/8",
                    "choices": [],
                },
            )

    event_ready = False
    if not check_event_exists(TEMPLATE_SLUG):
        logger.info("Creating new master template (%s)...", TEMPLATE_SLUG)
        creation = pretix_req(
            "POST",
            "events",
            {
                "name": {"en": "TEMPLATE: Standard Meetup"},
                "slug": TEMPLATE_SLUG,
                "live": False,
                "is_template": True,
                "currency": "USD",
                "date_from": "2026-12-31T18:00:00Z",
            },
        )
        if creation:
            event_ready = True
        else:
            logger.error("Failed to create template. Halting Pretix configuration.")
    else:
        logger.info("Template %r already exists.", TEMPLATE_SLUG)
        event_ready = True

    if event_ready:
        logger.info("Enforcing strict settings on template...")
        pretix_req(
            "PATCH",
            f"events/{TEMPLATE_SLUG}",
            {"live": False, "is_template": True},
        )
        pretix_req(
            "PATCH",
            f"events/{TEMPLATE_SLUG}/settings",
            {
                "max_items_per_order": 1,
                "invoice_address_asked": False,
                "attendee_names_asked": True,
                "attendee_names_required": True,
                "attendee_emails_asked": False,
                "name_scheme": "full",
                "order_email_asked_twice": False,
                "payment_term_last": None,
                "checkout_show_copy_answers_button": False,
                # Forum topic is the canonical event page; Pretix is the checkout
                # flow and should not compete in search results.
                "meta_noindex": True,
            },
        )

        items_resp = pretix_req("GET", f"events/{TEMPLATE_SLUG}/items")
        if items_resp and isinstance(items_resp, dict):
            items = items_resp.get("results", [])
            if not items:
                logger.info("Generating standard admission ticket...")
                item = pretix_req(
                    "POST",
                    f"events/{TEMPLATE_SLUG}/items",
                    {
                        "name": {"en": DEFAULT_ITEM_NAME},
                        "default_price": DEFAULT_ITEM_PRICE,
                        "active": True,
                        "admission": True,
                    },
                )
                if item and isinstance(item, dict):
                    pretix_req(
                        "POST",
                        f"events/{TEMPLATE_SLUG}/quotas",
                        {
                            "name": DEFAULT_QUOTA_NAME,
                            "size": 100,
                            "items": [item["id"]],
                        },
                    )

    logger.info("--- 2. DISCOURSE PROVISIONING ---")
    ensure_category_group_moderation_enabled()

    logger.info("Ensuring group %s...", MIGRATED_GROUP_NAME)
    groups = list_discourse_groups()
    existing_migrated = next((g for g in groups if g.get("name") == MIGRATED_GROUP_NAME), None)
    migrated_payload = {
        "group": {
            "name": MIGRATED_GROUP_NAME,
            "full_name": "Ansible Meetup - Migrated from Meetup Pro",
            "bio_raw": (
                "People who have migrated from Meetup Pro (meetup.com/pro/ansible) "
                "to the community-owned meetup platform.\n\n"
                "This group is used for tracking migration progress. "
                "Membership is managed automatically via invite links."
            ),
            "visibility_level": 3,
        }
    }
    if existing_migrated:
        discourse_req("PUT", f"groups/{existing_migrated['id']}.json", migrated_payload)
    else:
        discourse_req("POST", "admin/groups.json", migrated_payload)

    city_access = {}
    for city in CITIES:
        host_group, att_group, host_group_id = ensure_discourse_groups(city.slug, city.city)
        ensure_discourse_category(city.city, host_group, att_group, host_group_id)
        city_category_id = discourse_city_category_id(city.city)
        ensure_group_tracks_city_category(host_group, host_group_id, city_category_id)
        city_access[city_category_id] = (host_group, host_group_id)

    reconcile_organiser_category_access(city_access)

    ensure_user_field_options()

    logger.info("--- PROVISIONING COMPLETE ---")


if __name__ == "__main__":
    run_cli(main)
