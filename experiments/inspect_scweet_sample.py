"""Inspect relationship completeness in a saved Scweet sample.

This script reads the experiment output only. It does not contact X and does
not modify the production domain model or graph pipeline.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = PROJECT_ROOT / "data" / "scweet_sample.json"


def parse_timestamp(value: object) -> datetime | None:
    """Parse Scweet's Twitter date string, with an ISO-8601 fallback."""
    if not isinstance(value, str) or not value:
        return None
    for parser in (
        lambda text: datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y"),
        lambda text: datetime.fromisoformat(text.replace("Z", "+00:00")),
    ):
        try:
            return parser(value)
        except ValueError:
            continue
    return None


def tweet_id(record: dict[str, Any]) -> str | None:
    """Return the normalized tweet ID as a string when present."""
    value = record.get("tweet_id") or record.get("id")
    return str(value) if value else None


def referenced_id(record: dict[str, Any], relation: str) -> str | None:
    """Return a referenced target ID from Scweet's normalized record."""
    if relation == "reply":
        value = record.get("in_reply_to_tweet_id")
        return str(value) if value else None

    nested_key = "quoted_tweet" if relation == "quote" else "retweeted_tweet"
    nested = record.get(nested_key)
    if isinstance(nested, dict):
        value = nested.get("tweet_id") or nested.get("id")
        return str(value) if value else None
    return None


def relationship_summary(
    records: list[dict[str, Any]],
    relation: str,
    ids: set[str],
) -> tuple[int, list[str]]:
    """Count in-sample relationships and collect missing target IDs."""
    present_count = 0
    missing_targets: list[str] = []
    for record in records:
        target_id = referenced_id(record, relation)
        if not target_id:
            continue
        if target_id in ids:
            present_count += 1
        else:
            missing_targets.append(target_id)
    return present_count, missing_targets


def print_example(records: list[dict[str, Any]], relation: str) -> None:
    """Print the first available complete record for a relationship type."""
    for record in records:
        if referenced_id(record, relation):
            print(f"\nExample {relation}:\n")
            print(json.dumps(record, ensure_ascii=False, indent=2))
            return
    print(f"\nExample {relation}: none found")


def main() -> None:
    """Print sample quality and post-to-post relationship completeness."""
    if not SAMPLE_PATH.exists():
        raise FileNotFoundError(
            f"Run experiments/scweet_sample.py first: {SAMPLE_PATH}"
        )

    payload = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(
        isinstance(record, dict) for record in payload
    ):
        raise ValueError("The sample must be a JSON array of objects")
    records = payload

    ids = [tweet_id(record) for record in records]
    present_ids = {value for value in ids if value is not None}
    duplicate_ids = sorted(
        tweet_id for tweet_id, count in Counter(ids).items() if tweet_id and count > 1
    )
    timestamps = [
        timestamp
        for record in records
        if (timestamp := parse_timestamp(record.get("timestamp"))) is not None
    ]

    hashtag_count = sum(bool(record.get("hashtags")) for record in records)
    mention_count = sum(bool(record.get("mentions")) for record in records)
    reply_count, missing_replies = relationship_summary(records, "reply", present_ids)
    quote_count, missing_quotes = relationship_summary(records, "quote", present_ids)
    repost_count, missing_reposts = relationship_summary(records, "repost", present_ids)
    missing_targets = missing_replies + missing_quotes + missing_reposts

    print(f"Total records: {len(records)}")
    print(f"Unique tweet IDs: {len(present_ids)}")
    print(f"Duplicate IDs: {duplicate_ids}")
    print(f"Minimum timestamp: {min(timestamps) if timestamps else None}")
    print(f"Maximum timestamp: {max(timestamps) if timestamps else None}")
    print(f"Tweets containing hashtags: {hashtag_count}")
    print(f"Tweets containing mentions: {mention_count}")
    print(f"Replies with both posts present: {reply_count}")
    print(f"Quotes with both posts present: {quote_count}")
    print(f"Reposts with both posts present: {repost_count}")
    print(f"Referenced targets missing from dataset: {len(missing_targets)}")
    print(f"Missing reply targets: {len(missing_replies)}")
    print(f"Missing quote targets: {len(missing_quotes)}")
    print(f"Missing repost targets: {len(missing_reposts)}")

    print_example(records, "reply")
    print_example(records, "quote")
    print_example(records, "repost")


if __name__ == "__main__":
    main()
