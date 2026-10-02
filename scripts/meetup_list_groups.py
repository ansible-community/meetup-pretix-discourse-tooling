#!/usr/bin/env python3
"""List all groups in the Ansible Meetup Pro Network. Outputs CSV to stdout."""

from __future__ import annotations

import csv
import logging
import sys
from typing import Any

from meetup_pro_lib import (
    PRO_NETWORK,
    get_access_token,
    graphql,
    logger,
    pre_flight_checks,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def fetch_all_groups(token: str) -> list[dict[str, Any]]:
    query = """
    query ($urlname: ID!, $cursor: String) {
      proNetwork(urlname: $urlname) {
        groupsSearch(input: { first: 200, after: $cursor, filter: {} }) {
          totalCount
          pageInfo { endCursor hasNextPage }
          edges { node {
            id name urlname
            city country
            memberships { count }
            timezone
          } }
        }
      }
    }
    """
    groups: list[dict[str, Any]] = []
    cursor: str | None = None

    while True:
        data = graphql(token, query, {"urlname": PRO_NETWORK, "cursor": cursor})
        search = data.get("data", {}).get("proNetwork", {}).get("groupsSearch", {})

        for edge in search.get("edges", []):
            node = edge.get("node", {})
            groups.append(
                {
                    "id": node.get("id", ""),
                    "name": node.get("name", ""),
                    "urlname": node.get("urlname", ""),
                    "city": node.get("city", ""),
                    "country": node.get("country", ""),
                    "members": node.get("memberships", {}).get("count", 0),
                    "timezone": node.get("timezone", ""),
                }
            )

        page_info = search.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break

    return groups


def main() -> None:
    pre_flight_checks()

    logger.info("Authenticating with Meetup API...")
    token = get_access_token()

    logger.info("Fetching groups from Pro Network '%s'...", PRO_NETWORK)
    groups = fetch_all_groups(token)
    logger.info("Found %d groups", len(groups))

    writer = csv.DictWriter(sys.stdout, fieldnames=["id", "name", "urlname", "city", "country", "members", "timezone"])
    writer.writeheader()
    for group in sorted(groups, key=lambda g: g["name"]):
        writer.writerow(group)


if __name__ == "__main__":
    main()
