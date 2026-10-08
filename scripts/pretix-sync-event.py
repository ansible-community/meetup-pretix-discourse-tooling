#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from urllib.parse import urlparse

from ansible_events_lib import (
    discourse_req,
    logger,
    pre_flight_checks,
    pretix_req,
    run_cli,
    strip_discourse_block,
)


def main() -> None:
    pre_flight_checks()
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True, help="Pretix event slug")
    args = parser.parse_args()

    if not re.match(r"^[a-z0-9\-]+$", args.slug):
        logger.error(f"Invalid event slug {args.slug!r}: only lowercase alphanumerics and hyphens allowed")
        return

    event = pretix_req("GET", f"events/{args.slug}")
    if not event or not isinstance(event, dict):
        logger.error(f"Could not fetch event '{args.slug}' from Pretix.")
        return

    forum_url = event.get("meta_data", {}).get("forum_topic_url")
    if not forum_url:
        logger.error("No forum_topic_url found on event metadata.")
        return

    parsed = urlparse(forum_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        logger.error(f"Could not parse topic ID from URL: {forum_url}")
        return
    topic_id = path_parts[-1]
    if not topic_id.isdigit():
        logger.error(f"Topic ID is not numeric ({topic_id!r}) in URL: {forum_url}")
        return

    logger.info(f"Fetching Discourse Topic {topic_id}...")
    topic = discourse_req("GET", f"t/{topic_id}.json")
    if not topic or not isinstance(topic, dict):
        logger.error(f"Could not fetch topic {topic_id} from Discourse.")
        return

    title = topic.get("title")
    posts = topic.get("post_stream", {}).get("posts", [])
    if not posts:
        logger.error("Discourse topic has no posts.")
        return

    first_post_id = posts[0].get("id")
    if not first_post_id:
        logger.error("Could not extract first post ID from topic.")
        return

    logger.info(f"Fetching raw markdown for post {first_post_id}...")
    post_data = discourse_req("GET", f"posts/{first_post_id}.json")
    if not post_data or not isinstance(post_data, dict):
        logger.error(f"Could not fetch post {first_post_id} from Discourse.")
        return

    raw_markdown = post_data.get("raw", "")
    if not raw_markdown:
        logger.warning("Post has no raw markdown content.")
        return

    pretix_content = strip_discourse_block(raw_markdown)

    logger.info(f"Syncing updates to Pretix event '{args.slug}'...")
    pretix_req("PATCH", f"events/{args.slug}", {"name": {"en": title}})
    pretix_req("PATCH", f"events/{args.slug}/settings", {"frontpage_text": {"en": pretix_content}})

    logger.info("Sync complete.")


if __name__ == "__main__":
    run_cli(main)
