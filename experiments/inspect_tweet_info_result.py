from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from Scweet import Scweet


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_large_sample.json"
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8")
    )


def get_record(
    item: dict[str, Any],
) -> dict[str, Any]:
    record = item.get("record", {})

    if isinstance(record, dict):
        return record

    return {}


def get_tweet_id(
    item: dict[str, Any],
) -> str | None:
    value = item.get("tweet_id")

    if value is None:
        value = get_record(item).get("tweet_id")

    if value is None:
        return None

    return str(value)


def get_reply_target(
    record: dict[str, Any],
) -> str | None:
    value = record.get("in_reply_to_tweet_id")

    if value:
        return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get(
                "in_reply_to_status_id_str"
            )

            if value:
                return str(value)

    return None


def main() -> None:
    token = os.environ.get(
        "SCWEET_AUTH_TOKEN"
    )

    if not token:
        raise RuntimeError(
            "SCWEET_AUTH_TOKEN is not set."
        )

    data = load_json(SOURCE_PATH)

    records = data["records"]

    corpus_ids = {
        tweet_id
        for item in records
        if (
            tweet_id := get_tweet_id(item)
        )
    }

    target_id = None

    for item in records:
        record = get_record(item)

        candidate = get_reply_target(record)

        if (
            candidate
            and candidate not in corpus_ids
        ):
            target_id = candidate
            break

    if target_id is None:
        raise RuntimeError(
            "No missing reply target found."
        )

    print("=" * 70)
    print("TWEET INFO RESULT DIAGNOSTIC")
    print("=" * 70)

    print(f"Requested target ID: {target_id}")

    scweet = Scweet(
        auth_token=token
    )

    result = scweet.get_tweet_info(
        tweet_ids=[target_id],
        raw_json=True,
        save=False,
    )

    print()
    print(f"Result Python type: {type(result)}")

    if isinstance(result, list):
        print(f"List length: {len(result)}")

        if result:
            first = result[0]

            print()
            print(
                "First item Python type:",
                type(first),
            )

            if isinstance(first, dict):
                print()
                print("Top-level keys:")
                print(sorted(first.keys()))

                print()
                print("STRUCTURE:")
                print(
                    json.dumps(
                        first,
                        ensure_ascii=False,
                        indent=2,
                    )[:8000]
                )

    elif isinstance(result, dict):
        print()
        print("Top-level keys:")
        print(sorted(result.keys()))

        print()
        print("STRUCTURE:")
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )[:8000]
        )

    else:
        print()
        print(repr(result)[:8000])


if __name__ == "__main__":
    main()