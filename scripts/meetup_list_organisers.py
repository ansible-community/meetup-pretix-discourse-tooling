#!/usr/bin/env python3
"""List all organisers for each Ansible Meetup Pro group. Outputs CSV to stdout."""

from __future__ import annotations

import csv
import logging
import sys
import time

from meetup_pro_lib import (
    PRO_NETWORK,
    get_access_token,
    graphql,
    logger,
    pre_flight_checks,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def fetch_group_urlnames(token: str) -> list[dict[str, str]]:
    query = """
    query ($urlname: ID!, $cursor: String) {
      proNetwork(urlname: $urlname) {
        groupsSearch(input: { first: 200, after: $cursor, filter: {} }) {
          totalCount
          pageInfo { endCursor hasNextPage }
          edges { node { name urlname } }
        }
      }
    }
    """
    groups: list[dict[str, str]] = []
    cursor: str | None = None

    while True:
        data = graphql(token, query, {"urlname": PRO_NETWORK, "cursor": cursor})
        search = data.get("data", {}).get("proNetwork", {}).get("groupsSearch", {})
        for edge in search.get("edges", []):
            node = edge.get("node", {})
            groups.append({"name": node.get("name", ""), "urlname": node.get("urlname", "")})

        page_info = search.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break

    return groups


def fetch_group_organisers(token: str, group_urlname: str) -> list[dict[str, str]]:
    query = """
    query ($urlname: String!, $cursor: String) {
      groupByUrlname(urlname: $urlname) {
        memberships(input: { first: 200, after: $cursor, filter: { roles: [ORGANIZER, COORGANIZER, ASSISTANT_ORGANIZER, EVENT_ORGANIZER] } }) {
          pageInfo { endCursor hasNextPage }
          edges { node {
            role
            user {
              id name email
              memberSince
            }
          } }
        }
      }
    }
    """
    organisers: list[dict[str, str]] = []
    cursor: str | None = None

    while True:
        data = graphql(token, query, {"urlname": group_urlname, "cursor": cursor})
        group = data.get("data", {}).get("groupByUrlname")
        if not group:
            break

        memberships = group.get("memberships", {})
        for edge in memberships.get("edges", []):
            node = edge.get("node", {})
            user = node.get("user", {})
            organisers.append(
                {
                    "role": node.get("role", ""),
                    "full_name": user.get("name", ""),
                    "email": user.get("email", ""),
                    "member_since": user.get("memberSince", ""),
                }
            )

        page_info = memberships.get("pageInfo", {})
        if page_info.get("hasNextPage"):
            cursor = page_info["endCursor"]
        else:
            break

    return organisers


def main() -> None:
    pre_flight_checks()

    logger.info("Authenticating with Meetup API...")
    token = get_access_token()

    logger.info("Fetching groups from Pro Network '%s'...", PRO_NETWORK)
    groups = fetch_group_urlnames(token)
    logger.info("Found %d groups", len(groups))

    fieldnames = ["group_name", "group_urlname", "role", "full_name", "email", "member_since"]
    writer = csv.DictWriter(sys.stdout, fieldnames=fieldnames)
    writer.writeheader()

    for group in sorted(groups, key=lambda g: g["name"]):
        logger.info("Fetching organisers for %s...", group["urlname"])
        organisers = fetch_group_organisers(token, group["urlname"])

        for org in organisers:
            writer.writerow(
                {
                    "group_name": group["name"],
                    "group_urlname": group["urlname"],
                    **org,
                }
            )

        time.sleep(0.5)

    logger.info("Done.")


if __name__ == "__main__":
    main()
