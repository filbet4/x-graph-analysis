"""Collect a small conversation-centric Scweet sample.

This experiment searches for recent AI-related root posts and then collects
replies for selected roots. It is deliberately separate from the production
application and does not convert records into project domain models.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from Scweet import Scweet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "scweet_conversation_sample.json"
AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"

QUERY = "artificial intelligence"
SINCE = "2026-10-01"
UNTIL = "2026-10-11"

SEARCH_LIMIT = 100
ROOT_COUNT = 5
MIN_ROOT_REPLIES = 3
REPLIES_PER_ROOT = 50


def parse_timestamp(value: str | None) -> datetime:
    """Parse a timestamp returned by Scweet."""
    if not value:
        return datetime.min

    try:
        return datetime.strptime(
            value,
            "%a %b %d %H:%M:%S %z %Y",
        ).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def select_roots(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select deterministic non-reply posts to use as conversation roots."""
    candidates = [
        record
        for record in records
        if record.get("tweet_id")
        and record.get("in_reply_to_tweet_id") is None
    ]

    candidates.sort(
        key=lambda record: (
            -int(record.get("comments") or 0),
            -parse_timestamp(record.get("timestamp")).timestamp(),
            str(record.get("tweet_id")),
        )
    )

    preferred = [
        record
        for record in candidates
        if int(record.get("comments") or 0) >= MIN_ROOT_REPLIES
    ]

    selected = preferred[:ROOT_COUNT]

    if len(selected) < ROOT_COUNT:
        selected_ids = {record["tweet_id"] for record in selected}

        for record in candidates:
            if record["tweet_id"] in selected_ids:
                continue

            selected.append(record)
            selected_ids.add(record["tweet_id"])

            if len(selected) == ROOT_COUNT:
                break

    return selected


def main() -> None:
    """Collect roots and their conversation replies."""
    auth_token = os.environ.get(AUTH_TOKEN_ENV)
    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell before running this script"
        )

    scraper = Scweet(auth_token=auth_token)

    print("Searching for candidate root posts...")

    search_records = scraper.search(
        QUERY,
        since=SINCE,
        until=UNTIL,
        display_type="Latest",
        limit=SEARCH_LIMIT,
    )

    roots = select_roots(search_records)

    if not roots:
        raise RuntimeError("No suitable root posts were found")

    print(f"Selected {len(roots)} root posts:")

    for root in roots:
        print(
            f"  {root['tweet_id']} "
            f"(replies: {root.get('comments', 0)})"
        )

    # tweet_id -> complete Scweet record
    collected: dict[str, dict[str, Any]] = {}

    # Store roots first.
    for root in roots:
        collected[str(root["tweet_id"])] = root

    # Keep information about which records came from which root.
    conversations: dict[str, list[str]] = {}

    for index, root in enumerate(roots, start=1):
        root_id = str(root["tweet_id"])

        print(
            f"\nCollecting conversation {index}/{len(roots)} "
            f"for root {root_id}..."
        )

        try:
            replies = scraper.get_tweet_replies(
                root_id,
                limit=REPLIES_PER_ROOT,
            )
        except Exception as exc:
            print(f"  Failed to collect replies: {exc}")
            conversations[root_id] = []
            continue

        conversation_ids: list[str] = []

        for reply in replies:
            tweet_id = reply.get("tweet_id")

            if not tweet_id:
                continue

            tweet_id = str(tweet_id)

            collected[tweet_id] = reply
            conversation_ids.append(tweet_id)

        conversations[root_id] = conversation_ids

        print(f"  Received {len(replies)} records.")

    output = {
        "metadata": {
            "query": QUERY,
            "since": SINCE,
            "until": UNTIL,
            "display_type": "Latest",
            "search_limit": SEARCH_LIMIT,
            "root_count": len(roots),
            "replies_per_root_limit": REPLIES_PER_ROOT,
        },
        "root_ids": [str(root["tweet_id"]) for root in roots],
        "conversations": conversations,
        "records": list(collected.values()),
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print(f"Unique collected posts: {len(collected)}")
    print(f"Saved dataset to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()