#!/usr/bin/env python3
"""Reconcile Discourse groups/categories and Pretix template/teams to desired state.

Safe to run repeatedly. Designed for both initial setup and ongoing maintenance
as new cities are added to the CITIES registry.
"""

from __future__ import annotations

from ansible_events_lib import (
    ANSIBLE_PRIMARY_COLOR,
    ApiError,
    ATTENDEE_GROUP_PREFIX,
    STAFF_GROUP_NAME,
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
    ORGANIZERS_GROUP_RE,
    ORGANISER_PERMISSIONS,
    PRIVACY_POLICY_URL,
    TEMPLATE_PLUGINS,
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


def ensure_discourse_groups(city_slug: str, city_name: str) -> tuple[str, str, int]:
    host_group = f"{ORGANISERS_GROUP_PREFIX}-{city_slug}"
    attendee_group = f"{ATTENDEE_GROUP_PREFIX}-{city_slug}"

    def ensure_group(name: str, group: dict) -> int:
        groups = discourse_req("GET", "admin/groups.json").get("groups", [])
        existing = next((item for item in groups if item.get("name") == name), None)
        payload = {"group": group}
        if existing:
            logger.info("Reconciling group %s...", name)
            discourse_req("PUT", f"groups/{existing['id']}.json", payload)
            group_id = existing.get("id")
        else:
            logger.info("Creating group %s...", name)
            discourse_req("POST", "admin/groups.json", payload)
            groups = discourse_req("GET", "admin/groups.json").get("groups", [])
            created = next((item for item in groups if item.get("name") == name), None)
            group_id = created.get("id") if created else None
        if not isinstance(group_id, int):
            raise ApiError(f"Could not resolve Discourse group ID for {name!r}")
        return group_id

    host_group_id = ensure_group(host_group, {
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
                "visibility_level": 2,
            })
    ensure_group(attendee_group, {
                "name": attendee_group,
                "full_name": f"Ansible Meetup Attendees - {city_name}",
                "bio_raw": (
                    f"Notification subscription group for Ansible Meetup events in {city_name}.\n\n"
                    "Members receive notifications when new events are posted. "
                    "Membership is hidden (visible to forum admins only) to protect location privacy."
                ),
                "visibility_level": 3,
            })
    return host_group, attendee_group, host_group_id


def ensure_discourse_category(city_name: str, host_group: str, attendee_group: str, host_group_id: int) -> None:
    logger.info("Ensuring category Events > %s...", city_name)
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
    existing = next((c for c in categories if c.get("name", "").lower() == city_name.lower()
                     and c.get("parent_category_id") == DISCOURSE_PARENT_CATEGORY_ID), None)
    if existing:
        discourse_req("PUT", f"categories/{existing['id']}.json", desired)
    else:
        discourse_req("POST", "categories.json", desired)


def reconcile_organiser_category_moderators(city_moderators: dict[int, int]) -> None:
    """Keep each registered organiser group as moderator only on its own city category."""
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
    group_rows = discourse_req("GET", "admin/groups.json").get("groups")
    if not isinstance(group_rows, list):
        raise ApiError("Discourse groups response is missing groups")
    managed_group_ids = set(city_moderators.values())
    for group in group_rows:
        if not isinstance(group, dict):
            raise ApiError("Discourse groups response contains an invalid group")
        group_name = group.get("name")
        if isinstance(group_name, str) and ORGANIZERS_GROUP_RE.fullmatch(group_name):
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
        city_group_id = city_moderators.get(category_id)
        if city_group_id is not None:
            desired_ids.append(city_group_id)
        desired_ids = sorted(set(desired_ids))
        if desired_ids != sorted(set(current_ids)):
            discourse_req(
                "PUT",
                f"categories/{category_id}.json",
                {"moderating_group_ids": desired_ids},
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
        raise ApiError(
            "Discourse enable_category_group_moderation must be enabled to assign city organisers"
        )


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
    ensure_category_group_moderation_enabled()

    logger.info("--- 1. DISCOURSE PROVISIONING ---")

    logger.info("Ensuring group %s...", STAFF_GROUP_NAME)
    groups = discourse_req("GET", "admin/groups.json").get("groups", [])
    existing_admin = next((g for g in groups if g.get("name") == STAFF_GROUP_NAME), None)
    admin_payload = {"group": {
                "name": STAFF_GROUP_NAME,
                "full_name": "Ansible Meetup Admins",
                "bio_raw": (
                    "Ansible Community Team members with global admin access to the meetup platform.\n\n"
                    "**Requirements:** Members must have 2FA enabled and be approved by the "
                    "Community Engineering lead.\n\n"
                    "This group grants Pretix site-wide admin access across all organisers and events."
                ),
                "visibility_level": 4,
            }}
    if existing_admin:
        discourse_req("PUT", f"groups/{existing_admin['id']}.json", admin_payload)
    else:
        discourse_req("POST", "admin/groups.json", admin_payload)

    logger.info("Ensuring group %s...", MIGRATED_GROUP_NAME)
    groups = discourse_req("GET", "admin/groups.json").get("groups", [])
    existing_migrated = next((g for g in groups if g.get("name") == MIGRATED_GROUP_NAME), None)
    migrated_payload = {"group": {
                "name": MIGRATED_GROUP_NAME,
                "full_name": "Ansible Meetup - Migrated from Meetup Pro",
                "bio_raw": (
                    "People who have migrated from Meetup Pro (meetup.com/pro/ansible) "
                    "to the community-owned meetup platform.\n\n"
                    "This group is used for tracking migration progress. "
                    "Membership is managed automatically via invite links."
                ),
                "visibility_level": 3,
            }}
    if existing_migrated:
        discourse_req("PUT", f"groups/{existing_migrated['id']}.json", migrated_payload)
    else:
        discourse_req("POST", "admin/groups.json", migrated_payload)

    city_moderators = {}
    for city in CITIES:
        host_group, att_group, host_group_id = ensure_discourse_groups(city.slug, city.city)
        ensure_discourse_category(city.city, host_group, att_group, host_group_id)
        city_category_id = discourse_city_category_id(city.city)
        city_moderators[city_category_id] = host_group_id

    reconcile_organiser_category_moderators(city_moderators)

    ensure_user_field_options()

    logger.info("--- 2. PRETIX PROVISIONING ---")
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
                "plugins": TEMPLATE_PLUGINS,
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
            {"live": False, "is_template": True, "plugins": TEMPLATE_PLUGINS},
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

    logger.info("Provisioning regional Pretix Teams...")
    all_teams = pretix_list_all("teams")
    existing_teams = {t["name"]: t for t in all_teams}
    for city in CITIES:
        desired_team = {
            "name": city.team_name,
            "all_event_permissions": False,
            "limit_event_permissions": ORGANISER_PERMISSIONS,
            "limit_events": existing_teams.get(city.team_name, {}).get("limit_events", []),
        }
        if city.team_name in existing_teams:
            team_resp = pretix_req("GET", f"teams/{existing_teams[city.team_name]['id']}")
            desired_team["limit_events"] = team_resp.get("limit_events", [])
            pretix_req("PATCH", f"teams/{existing_teams[city.team_name]['id']}", desired_team)
        else:
            pretix_req(
                "POST",
                "teams",
                desired_team,
            )

    logger.info("--- PROVISIONING COMPLETE ---")


if __name__ == "__main__":
    run_cli(main)
