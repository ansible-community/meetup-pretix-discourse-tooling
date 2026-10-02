#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta

from ansible_events_lib import (
    CODE_OF_CONDUCT_URL,
    DEFAULT_ITEM_NAME,
    DEFAULT_ITEM_PRICE,
    DEFAULT_QUOTA_NAME,
    DISCOURSE_EVENTS_CATEGORY_ID,
    DISCOURSE_URL,
    EVENT_NAME_PREFIX,
    EVENTS_FORUM_URL,
    HOST_GROUP_PREFIX,
    ORGANISER_PERMISSIONS,
    ORGANISER_TEAM_PREFIX,
    ORGANIZER_SLUG,
    PRETIX_URL,
    TEMPLATE_SLUG,
    check_event_exists,
    discourse_req,
    discourse_user_exists,
    discourse_user_in_group,
    get_city,
    logger,
    pre_flight_checks,
    pretix_list_all,
    pretix_req,
    strip_discourse_block,
)


def print_social_media_copy(*, city: str, dt: datetime, forum_url: str) -> None:
    print("\n" + "=" * 80)
    print("SOCIAL MEDIA COPY (ready to paste)")
    print("=" * 80 + "\n")

    print("📱 X / TWITTER:")
    print("-" * 40)
    twitter_text = f"Join us at {EVENT_NAME_PREFIX} {city} on {dt.strftime('%B %d')}! Connect with automation enthusiasts, share knowledge, and level up your Ansible skills. #Ansible #Meetup #OpenSource\n\n{forum_url}"
    if len(twitter_text) > 280:
        twitter_text = f"{EVENT_NAME_PREFIX} {city} - {dt.strftime('%B %d')}! Join us for automation talks, networking & community. #Ansible #Meetup #OpenSource\n\n{forum_url}"
    print(twitter_text)
    print(f"({len(twitter_text)} chars)\n")

    print("🦋 BLUESKY:")
    print("-" * 40)
    bluesky_text = f"Calling all automation enthusiasts! Join us at {EVENT_NAME_PREFIX} {city} on {dt.strftime('%B %d, %Y')}. Learn, share, and connect with the community. #Ansible #DevOps #Automation\n\n{forum_url}"
    if len(bluesky_text) > 300:
        bluesky_text = f"{EVENT_NAME_PREFIX} {city} - {dt.strftime('%B %d')}! Automation talks, networking & community. #Ansible #DevOps #Automation\n\n{forum_url}"
    print(bluesky_text)
    print(f"({len(bluesky_text)} chars)\n")

    print("🐘 MASTODON:")
    print("-" * 40)
    mastodon_text = f"""{EVENT_NAME_PREFIX} coming to {city} on {dt.strftime("%B %d, %Y")}!

Whether you're an Ansible expert or just getting started, join us for:
✨ Real-world use cases & best practices
🤝 Networking with local DevOps engineers
💡 Q&A with experienced practitioners

RSVP & details: {forum_url}

#Ansible #Meetup #DevOps #Automation #OpenSource #InfrastructureAsCode"""
    print(mastodon_text)
    print(f"({len(mastodon_text)} chars)\n")

    print("💼 LINKEDIN:")
    print("-" * 40)
    linkedin_text = f"""Exciting news for the automation community in {city}!

We're hosting an Ansible Community Meetup on {dt.strftime("%B %d, %Y")}, and you're invited!

This is a fantastic opportunity to:
• Hear real-world Ansible use cases and best practices
• Network with local DevOps engineers and system administrators
• Get your questions answered by experienced practitioners
• Be part of the global Ansible community right in your city

Whether you're already using Ansible in production or just exploring automation tools, you'll find valuable insights and connections at this event.

RSVP and event details: {forum_url}

Tag someone who should join us! #Ansible #DevOps #Automation #InfrastructureAsCode #CommunityMeetup"""
    print(linkedin_text)
    print(f"({len(linkedin_text)} chars)\n")

    print("🤖 REDDIT (r/ansible):")
    print("-" * 40)
    reddit_text = f"""**{EVENT_NAME_PREFIX} in {city} - {dt.strftime("%B %d, %Y")}**

Hey r/ansible! We're organizing a local meetup for the Ansible community in {city}, and I wanted to share it here in case any of you are in the area.

We'll have talks from community members sharing their real-world experiences, time for networking, and Q&A. Whether you're deep into Ansible automation or just getting started, it's a great chance to connect with others doing similar work.

Event details and RSVP: {forum_url}

Feel free to reach out if you have questions or want to propose a talk topic!"""
    print(reddit_text + "\n")

    print("📰 HACKER NEWS:")
    print("-" * 40)
    hn_text = f"Ansible Community Meetup – {city} ({dt.strftime('%B %Y')})"
    print(hn_text)
    print(f"{forum_url}\n")

    print("=" * 80)
    print("END OF SOCIAL MEDIA COPY")
    print("=" * 80 + "\n")


def main() -> None:
    pre_flight_checks()

    parser = argparse.ArgumentParser(description="Generate an Ansible Meetup with Discourse Calendar integration.")
    parser.add_argument("--city", required=True, help="E.g., London")
    parser.add_argument("--date", required=True, help="Event local time (e.g., '2026-10-31T18:00:00')")
    parser.add_argument("--capacity", required=True, type=int, help="Venue capacity limit")
    parser.add_argument("--organiser", required=True, help="Discourse username of the local organiser")
    parser.add_argument("--venue", default=None, help="Venue name (e.g., 'Metro Bank Offices')")
    parser.add_argument("--address", default=None, help="Venue address (e.g., '1 Southampton Row, London WC1B 5HA')")
    args = parser.parse_args()

    if not re.match(r"^[A-Za-z \-]+$", args.city):
        logger.error("Invalid city name %r: only letters, spaces, and hyphens allowed", args.city)
        raise SystemExit(1)

    city_info = get_city(args.city)
    event_timezone = city_info.timezone if city_info else "UTC"
    city_title = args.city.title()
    city_slug = args.city.lower().replace(" ", "-")
    expected_group = f"{HOST_GROUP_PREFIX}-{city_slug}"

    logger.info("Validating organiser @%s...", args.organiser)
    if not discourse_user_exists(args.organiser):
        logger.error("Discourse user %r does not exist.", args.organiser)
        raise SystemExit(1)

    if not discourse_user_in_group(args.organiser, expected_group):
        logger.error("User %r is not in group %r. Add them to the group first.", args.organiser, expected_group)
        raise SystemExit(1)

    dt = datetime.fromisoformat(args.date.rstrip("Z"))
    end_dt = dt + timedelta(hours=3)

    start_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
    event_name = f"{EVENT_NAME_PREFIX} {city_title}"
    target_slug = f"{args.city.lower().replace(' ', '-')}-{dt.strftime('%b').lower()}-{dt.strftime('%Y')}"

    if args.venue and args.address:
        venue_display = f"{args.venue}, {args.address}"
    elif args.venue or args.address:
        venue_display = args.venue or args.address
    else:
        venue_display = "*To be announced*"

    if check_event_exists(target_slug):
        logger.error("Pretix event %r already exists. Aborting to prevent duplicates.", target_slug)
        raise SystemExit(1)

    logger.info("Drafting initial forum post on behalf of @%s...", args.organiser)

    initial_markdown = f"""[event start="{start_str}" end="{end_str}" timezone="{event_timezone}" minimal="true" name="{event_name}" url="https://link-pending.local"]
[/event]

---

## {event_name}

Join us for an evening of automation, collaboration, and community! Whether you're an Ansible expert or just getting started, this meetup is your chance to connect with fellow automation enthusiasts and share your experiences.

### Details

| | |
|---|---|
| **Date** | {dt.strftime("%A, %B %d, %Y")} |
| **Time** | {dt.strftime("%H:%M")} - {end_dt.strftime("%H:%M")} ({event_timezone}) |
| **Venue** | {venue_display} |
| **Cost** | Free |
| **Organiser** | @{args.organiser} |

### Agenda

| Time | Topic | Speaker |
|------|-------|---------|
| {dt.strftime("%H:%M")} | Welcome & introductions | @{args.organiser} |
| *TBD* | *Open for proposals* | *Your name here!* |
| *TBD* | *Open for proposals* | *Your name here!* |
| {end_dt.strftime("%H:%M")} | Wrap-up & networking | |

### Speakers

*Organisers: update this section as speakers are confirmed.*

**@{args.organiser}** — *Meetup organiser. [Edit to add a short bio.]*

<!-- Copy this block for each confirmed speaker:
**@username** — *Brief bio: role, company, what they're passionate about in automation.*
**Talk:** *Title of their talk*
-->

Want to present? Reply below with your topic, a short abstract, and a one-line bio!

### RSVP

*[RSVP link pending...]*

RSVP so we can manage capacity and send you a QR code for check-in. You'll get a confirmation email with your ticket and a calendar invite.

### What to Bring

- Your laptop (optional — for hands-on demos)
- Questions about Ansible, automation, or your infrastructure challenges
- A friend who might be interested!

### Share

Attending? Help spread the word:

> I'm going to {event_name} on {dt.strftime("%B %d")}! Free Ansible automation meetup with talks, networking, and community. RSVP: [link]

### Accessibility

*Organisers: please update this section with venue accessibility details — step-free access, parking, public transport, dietary options.*

### Getting There

*Organisers: update with directions, nearest public transport, parking info.*

### Connect

Questions? Talk proposals? Need a ride? Reply below — this topic is your space to coordinate before the event.

[Browse all Ansible Community Meetups]({EVENTS_FORUM_URL}) | [Code of Conduct]({CODE_OF_CONDUCT_URL})

*Organised by @{args.organiser} on behalf of the Ansible Community.*
"""

    import json as json_mod

    offers: dict[str, str] = {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD",
        "availability": "https://schema.org/InStock",
    }
    jsonld: dict[str, object] = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event_name,
        "startDate": start_str,
        "endDate": end_str,
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "eventStatus": "https://schema.org/EventScheduled",
        "organizer": {"@type": "Organization", "name": "Ansible Community", "url": DISCOURSE_URL},
        "isAccessibleForFree": True,
        "offers": offers,
    }
    if args.venue or args.address:
        location: dict[str, object] = {"@type": "Place"}
        if args.venue:
            location["name"] = args.venue
        if args.address:
            location["address"] = {
                "@type": "PostalAddress",
                "streetAddress": args.address,
                "addressLocality": city_title,
            }
        jsonld["location"] = location

    initial_markdown += f'\n<script type="application/ld+json">\n{json_mod.dumps(jsonld, indent=2)}\n</script>\n'

    topic_resp = discourse_req(
        "POST",
        "posts.json",
        {
            "title": f"{EVENT_NAME_PREFIX}: {city_title} - {dt.strftime('%B %Y')}",
            "raw": initial_markdown,
            "category": DISCOURSE_EVENTS_CATEGORY_ID,
        },
        run_as=args.organiser,
    )

    if not topic_resp or not isinstance(topic_resp, dict):
        logger.error("Failed to create Discourse topic. Aborting Pretix creation.")
        raise SystemExit(1)

    post_id = topic_resp["id"]
    forum_url = f"{DISCOURSE_URL}/t/{topic_resp['topic_slug']}/{topic_resp['topic_id']}"
    logger.info("Forum post created: %s", forum_url)

    logger.info("Cloning Pretix event from %r...", TEMPLATE_SLUG)

    pretix_event = pretix_req(
        "POST",
        "events",
        {
            "name": {"en": event_name},
            "slug": target_slug,
            "date_from": args.date,
            "date_to": end_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "timezone": event_timezone,
            "clone_from": TEMPLATE_SLUG,
            "meta_data": {"forum_topic_url": forum_url},
        },
    )

    if not pretix_event or not isinstance(pretix_event, dict):
        logger.error("Failed to create Pretix event.")
        raise SystemExit(1)

    final_slug = pretix_event.get("slug")
    pretix_public_url = f"{PRETIX_URL}/{ORGANIZER_SLUG}/{final_slug}/"
    logger.info("Pretix event created: %s", pretix_public_url)

    logger.info("Updating Discourse post with Pretix URL...")

    jsonld["url"] = forum_url
    offers["url"] = pretix_public_url
    updated_jsonld = f'<script type="application/ld+json">\n{json_mod.dumps(jsonld, indent=2)}\n</script>'

    final_markdown = (
        initial_markdown.replace(
            'url="https://link-pending.local"',
            f'url="{pretix_public_url}"',
        )
        .replace(
            "*[RSVP link pending...]*",
            f"**[Click here to RSVP via Pretix]({pretix_public_url})**",
        )
        .replace(
            "RSVP: [link]",
            f"RSVP: {forum_url}",
        )
    )

    final_markdown = re.sub(
        r'<script type="application/ld\+json">.*?</script>',
        updated_jsonld,
        final_markdown,
        flags=re.DOTALL,
    )

    update_resp = discourse_req(
        "PUT", f"posts/{post_id}.json", {"post": {"raw": final_markdown}}, run_as=args.organiser
    )
    if not update_resp:
        logger.warning("Failed to update Discourse post with Pretix URL")

    logger.info("Syncing description to Pretix frontpage...")
    pretix_content = strip_discourse_block(final_markdown)
    settings_resp = pretix_req("PATCH", f"events/{final_slug}/settings", {"frontpage_text": {"en": pretix_content}})
    if not settings_resp:
        logger.warning("Failed to sync description to Pretix frontpage")

    logger.info("Adjusting venue capacity to %d...", args.capacity)
    quotas = pretix_req("GET", f"events/{final_slug}/quotas")

    if quotas and isinstance(quotas, dict) and quotas.get("results"):
        pretix_req("PATCH", f"events/{final_slug}/quotas/{quotas['results'][0]['id']}", {"size": args.capacity})
    else:
        logger.info("No quota inherited from template. Generating new quota...")
        items_resp = pretix_req("GET", f"events/{final_slug}/items")
        items = items_resp.get("results", []) if isinstance(items_resp, dict) else []
        if not items:
            logger.info("No items found. Generating standard admission item...")
            item = pretix_req(
                "POST",
                f"events/{final_slug}/items",
                {
                    "name": {"en": DEFAULT_ITEM_NAME},
                    "default_price": DEFAULT_ITEM_PRICE,
                    "active": True,
                    "admission": True,
                },
            )
            if not item or not isinstance(item, dict):
                logger.error("Failed to create admission item. Cannot set quota.")
                raise SystemExit(1)
            item_id = item["id"]
        else:
            item_id = items[0]["id"]

        quota_resp = pretix_req(
            "POST",
            f"events/{final_slug}/quotas",
            {
                "name": DEFAULT_QUOTA_NAME,
                "size": args.capacity,
                "items": [item_id],
            },
        )
        if not quota_resp:
            logger.warning("Failed to create quota for event")

    logger.info("Setting wallet pass back field to forum URL...")
    items_for_pass = pretix_req("GET", f"events/{final_slug}/items")
    if items_for_pass and isinstance(items_for_pass, dict):
        for item in items_for_pass.get("results", []):
            pretix_req(
                "PATCH",
                f"events/{final_slug}/items/{item['id']}",
                {
                    "meta_data": {"pretix_passbook_backfield": f"Event details and discussion: {forum_url}"},
                },
            )

    logger.info("Publishing Pretix event...")
    publish_resp = pretix_req("PATCH", f"events/{final_slug}", {"live": True})
    if not publish_resp:
        logger.warning("Failed to publish Pretix event")

    logger.info("Assigning event to local Organisers Team...")
    team_name = f"{ORGANISER_TEAM_PREFIX} - {city_title}"
    all_teams = pretix_list_all("teams")
    for t in all_teams:
        if t["name"] == team_name:
            full_team = pretix_req("GET", f"teams/{t['id']}")
            if not full_team or not isinstance(full_team, dict):
                logger.warning("Failed to fetch team %r details", team_name)
                break
            limit_events = full_team.get("limit_events", [])
            if final_slug not in limit_events:
                limit_events.append(final_slug)

            team_update = pretix_req(
                "PATCH",
                f"teams/{t['id']}",
                {
                    "limit_events": limit_events,
                    "all_event_permissions": False,
                    "limit_event_permissions": ORGANISER_PERMISSIONS,
                },
            )
            if not team_update:
                logger.warning("Failed to assign event to team %r", team_name)
            break

    logger.info("--- EVENT SUCCESSFULLY PROVISIONED ---")
    print_social_media_copy(city=city_title, dt=dt, forum_url=forum_url)


if __name__ == "__main__":
    main()
