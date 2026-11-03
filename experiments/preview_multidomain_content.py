"""Preview actual text from multidomain conversations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_multidomain_conversations.json"
)

PREVIEW_REPLIES = 10


def get_text(record: dict[str, Any]) -> str:
    """Extract tweet text from common Scweet fields."""
    for key in ("text", "full_text", "tweet_text"):
        value = record.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    value = legacy.get("full_text")

    if isinstance(value, str):
        return value.strip()

    return "<NO TEXT>"


def clean_text(text: str) -> str:
    return " ".join(text.split())


def main() -> None:
    data = json.loads(
        INPUT_PATH.read_text(encoding="utf-8")
    )

    records = {
        str(item["tweet_id"]): item
        for item in data["records"]
    }

    print("=== MULTIDOMAIN CONTENT PREVIEW ===")

    for root_info in data["selected_roots"]:
        root_id = str(root_info["tweet_id"])
        domain = root_info["sampling_domain"]

        root_item = records.get(root_id)

        if root_item is None:
            continue

        root_text = clean_text(
            get_text(root_item["record"])
        )

        print()
        print("=" * 80)
        print(f"DOMAIN: {domain.upper()}")
        print(f"ROOT: {root_id}")
        print()
        print(f"ROOT TEXT: {root_text}")
        print()
        print("REPLIES:")

        replies = []

        for tweet_id, item in records.items():
            record = item["record"]

            parent = record.get(
                "in_reply_to_tweet_id"
            )

            if parent and str(parent) == root_id:
                replies.append(
                    (
                        tweet_id,
                        clean_text(
                            get_text(record)
                        ),
                    )
                )

        for index, (tweet_id, text) in enumerate(
            replies[:PREVIEW_REPLIES],
            start=1,
        ):
            print()
            print(
                f"  [{index}] {tweet_id}: {text}"
            )

        print()
        print(
            f"Direct replies available: "
            f"{len(replies)}"
        )


if __name__ == "__main__":
    main()