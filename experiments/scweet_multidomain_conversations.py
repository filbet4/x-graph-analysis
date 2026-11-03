"""Collect conversation-centered samples from multiple domains on X."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Scweet import Scweet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "scweet_multidomain_sample.json"
OUTPUT_PATH = PROJECT_ROOT / "data" / "scweet_multidomain_conversations.json"

AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"

ROOTS_PER_DOMAIN = 3
REPLIES_PER_ROOT = 50

DOMAINS = ("politics", "sport", "pop_culture")


def get_record(item: dict[str, Any]) -> dict[str, Any]:
    return item["record"]


def get_sampling_domains(item: dict[str, Any]) -> set[str]:
    return {
        source["domain"]
        for source in item.get("sampling_sources", [])
    }


def is_reply(record: dict[str, Any]) -> bool:
    return bool(record.get("in_reply_to_tweet_id"))


def get_reply_count(record: dict[str, Any]) -> int:
    """Read reply/comment count from common Scweet fields."""
    possible_values = [
        record.get("comments"),
        record.get("reply_count"),
        record.get("replies"),
    ]

    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    possible_values.append(legacy.get("reply_count"))

    for value in possible_values:
        if isinstance(value, int):
            return value

        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                continue

    return 0


def select_roots(
    items: list[dict[str, Any]],
    domain: str,
) -> list[dict[str, Any]]:
    """Select several conversation roots for one sampling domain."""
    candidates = []

    for item in items:
        if domain not in get_sampling_domains(item):
            continue

        record = get_record(item)

        # We want conversation starters rather than posts that are
        # themselves replies to another post.
        if is_reply(record):
            continue

        candidates.append(item)

    # We need roots that actually have a chance of producing a conversation.
    candidates.sort(
        key=lambda item: get_reply_count(get_record(item)),
        reverse=True,
    )

    roots_with_replies = [
        item
        for item in candidates
        if get_reply_count(get_record(item)) > 0
    ]

    return roots_with_replies[:ROOTS_PER_DOMAIN]


def add_record(
    collected: dict[str, dict[str, Any]],
    record: dict[str, Any],
    *,
    role: str,
    root_id: str,
    sampling_domain: str,
) -> None:
    tweet_id = record.get("tweet_id")

    if not tweet_id:
        return

    tweet_id = str(tweet_id)

    if tweet_id not in collected:
        collected[tweet_id] = {
            "record": record,
            "collection_contexts": [],
        }

    context = {
        "role": role,
        "root_id": root_id,
        "sampling_domain": sampling_domain,
    }

    if context not in collected[tweet_id]["collection_contexts"]:
        collected[tweet_id]["collection_contexts"].append(context)


def main() -> None:
    auth_token = os.environ.get(AUTH_TOKEN_ENV)

    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell before running this script"
        )

    source_data = json.loads(
        INPUT_PATH.read_text(encoding="utf-8")
    )

    items = source_data["records"]

    scraper = Scweet(auth_token=auth_token)

    collected: dict[str, dict[str, Any]] = {}
    selected_roots: list[dict[str, Any]] = []
    conversation_results: list[dict[str, Any]] = []

    for domain in DOMAINS:
        roots = select_roots(items, domain)

        print()
        print(f"=== {domain.upper()} ===")
        print(f"Selected roots: {len(roots)}")

        if len(roots) < ROOTS_PER_DOMAIN:
            print(
                f"WARNING: wanted {ROOTS_PER_DOMAIN}, "
                f"but found only {len(roots)} suitable roots."
            )

        for item in roots:
            root_record = get_record(item)
            root_id = str(root_record["tweet_id"])
            reply_count = get_reply_count(root_record)

            print()
            print(
                f"Root {root_id} "
                f"(reported replies: {reply_count})"
            )

            selected_roots.append(
                {
                    "tweet_id": root_id,
                    "sampling_domain": domain,
                    "reported_reply_count": reply_count,
                    "sampling_sources": item.get(
                        "sampling_sources",
                        [],
                    ),
                }
            )

            add_record(
                collected,
                root_record,
                role="root",
                root_id=root_id,
                sampling_domain=domain,
            )

            try:
                replies = scraper.get_tweet_replies(
                    root_id,
                    limit=REPLIES_PER_ROOT,
                )
            except Exception as exc:
                print(f"  Failed to fetch replies: {exc}")

                conversation_results.append(
                    {
                        "root_id": root_id,
                        "sampling_domain": domain,
                        "status": "failed",
                        "error": str(exc),
                        "replies_received": 0,
                    }
                )
                continue

            print(f"  Received {len(replies)} replies.")

            conversation_results.append(
                {
                    "root_id": root_id,
                    "sampling_domain": domain,
                    "status": "ok",
                    "replies_received": len(replies),
                }
            )

            for reply in replies:
                add_record(
                    collected,
                    reply,
                    role="conversation",
                    root_id=root_id,
                    sampling_domain=domain,
                )

    output_records = []

    for tweet_id, item in collected.items():
        output_records.append(
            {
                "tweet_id": tweet_id,
                "collection_contexts": item[
                    "collection_contexts"
                ],
                "record": item["record"],
            }
        )

    output = {
        "metadata": {
            "experiment": "multidomain_conversations",
            "collected_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "roots_per_domain": ROOTS_PER_DOMAIN,
            "replies_per_root": REPLIES_PER_ROOT,
            "domains": list(DOMAINS),
            "important_note": (
                "Sampling domain describes how a root was found. "
                "It is not the final content classification."
            ),
        },
        "selected_roots": selected_roots,
        "conversation_results": conversation_results,
        "records": output_records,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print()
    print("=== COLLECTION FINISHED ===")
    print(f"Selected roots: {len(selected_roots)}")
    print(f"Unique collected posts: {len(collected)}")
    print(f"Saved dataset to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()