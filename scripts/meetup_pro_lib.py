"""Shared client for the Meetup Pro Network GraphQL API (JWT OAuth2)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import jwt
import requests

logger = logging.getLogger("meetup_export")

MEETUP_API_URL = "https://api.meetup.com/gql-ext"
MEETUP_TOKEN_URL = "https://secure.meetup.com/oauth2/access"
PRO_NETWORK = "ansible"


def pre_flight_checks() -> None:
    """Validate required Meetup API environment variables."""
    required = ["MEETUP_CLIENT_KEY", "MEETUP_SIGNING_KEY_ID", "MEETUP_MEMBER_ID", "MEETUP_PRIVATE_KEY"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        logger.error("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)

    key_path = os.environ["MEETUP_PRIVATE_KEY"]
    if not Path(key_path).exists():
        logger.error("Private key file not found: %s", key_path)
        sys.exit(1)


def get_access_token() -> str:
    """Authenticate with Meetup OAuth2 and return an access token."""
    client_key = os.environ["MEETUP_CLIENT_KEY"]
    signing_key_id = os.environ["MEETUP_SIGNING_KEY_ID"]
    member_id = os.environ["MEETUP_MEMBER_ID"]
    private_key = Path(os.environ["MEETUP_PRIVATE_KEY"]).read_text()

    signed_jwt = jwt.encode(
        {"sub": member_id, "iss": client_key, "aud": "api.meetup.com", "exp": int(time.time()) + 120},
        private_key,
        algorithm="RS256",
        headers={"kid": signing_key_id, "typ": "JWT", "alg": "RS256"},
    )

    resp = requests.post(
        MEETUP_TOKEN_URL,
        data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": signed_jwt},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("Meetup auth failed: HTTP %d", resp.status_code)
        sys.exit(1)

    token = resp.json().get("access_token")
    if not token:
        logger.error("No access_token in response")
        sys.exit(1)
    return token


def graphql(token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a GraphQL query with rate limit handling."""
    resp = requests.post(
        MEETUP_API_URL,
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if resp.status_code == 429:
        wait = 60
        logger.warning("Rate limited, waiting %ds...", wait)
        time.sleep(wait)
        return graphql(token, query, variables)
    if resp.status_code != 200:
        logger.error("GraphQL request failed: HTTP %d", resp.status_code)
        return {}
    return resp.json()
