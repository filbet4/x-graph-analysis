"""Test whether X search through Scweet respects the lang:pl operator.

The experiment compares selected queries with and without the
lang:pl search operator.

It is intentionally small to reduce the number of requests.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Scweet import Scweet


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_language_filter_test.json"
)

AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"

SINCE = "2026-10-04"
UNTIL = "2026-10-12"
DISPLAY_TYPE = "Latest"

LIMIT_PER_QUERY = 15

BASE_QUERIES = [
    "Iga Świątek",
    "Donald Tusk",
    "Taco Hemingway",
]


def extract_text(record: dict[str, Any]) -> str:
    """Extract tweet text from a Scweet record."""
    for key in ("text", "full_text", "tweet_text"):
        value = record.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get("full_text")

            if isinstance(value, str):
                return value.strip()

    return ""


def shorten(text: str, limit: int = 220) -> str:
    """Shorten tweet text for terminal preview."""
    text = " ".join(text.split())

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def main() -> None:
    """Compare normal queries with lang:pl queries."""
    auth_token = os.environ.get(AUTH_TOKEN_ENV)

    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell before running this script"
        )

    scraper = Scweet(auth_token=auth_token)

    results: list[dict[str, Any]] = []

    for base_query in BASE_QUERIES:
        variants = [
            ("normal", base_query),
            ("lang_pl", f"{base_query} lang:pl"),
        ]

        for variant, query in variants:
            print()
            print("=" * 80)
            print(f"BASE QUERY: {base_query}")
            print(f"VARIANT:    {variant}")
            print(f"SEARCH:     {query!r}")
            print("=" * 80)

            try:
                records = scraper.search(
                    query,
                    since=SINCE,
                    until=UNTIL,
                    display_type=DISPLAY_TYPE,
                    limit=LIMIT_PER_QUERY,
                )
            except Exception as exc:
                print(f"Search failed: {exc}")

                results.append(
                    {
                        "base_query": base_query,
                        "variant": variant,
                        "query": query,
                        "status": "failed",
                        "error": str(exc),
                        "returned_records": 0,
                        "records": [],
                    }
                )
                continue

            print(f"Received: {len(records)}")

            saved_records = []

            for index, record in enumerate(
                records,
                start=1,
            ):
                tweet_id = str(
                    record.get("tweet_id", "")
                )

                text = extract_text(record)

                saved_records.append(
                    {
                        "tweet_id": tweet_id,
                        "text": text,
                        "record": record,
                    }
                )

                print()
                print(f"[{index}] {tweet_id}")
                print(shorten(text))

            results.append(
                {
                    "base_query": base_query,
                    "variant": variant,
                    "query": query,
                    "status": "ok",
                    "returned_records": len(records),
                    "records": saved_records,
                }
            )

    output = {
        "metadata": {
            "experiment": "language_filter_test",
            "collected_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "since": SINCE,
            "until": UNTIL,
            "display_type": DISPLAY_TYPE,
            "limit_per_query": LIMIT_PER_QUERY,
            "base_queries": BASE_QUERIES,
            "purpose": (
                "Test whether the lang:pl search operator "
                "improves Polish-language filtering."
            ),
        },
        "results": results,
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
    print("=" * 80)
    print("LANGUAGE FILTER TEST FINISHED")
    print("=" * 80)

    for result in results:
        print(
            f"{result['base_query']} | "
            f"{result['variant']}: "
            f"{result['returned_records']} "
            f"({result['status']})"
        )

    print()
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()