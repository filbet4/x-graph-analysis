"""Collect a small multidomain Scweet sample for offline inspection.

The experiment collects recent X posts from three broad domains:
politics, sport and pop culture.

Search queries are treated only as sampling sources. They do not determine
the final domain classification of a post.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Scweet import Scweet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "scweet_multidomain_sample.json"

AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"

SINCE = "2026-10-04"
UNTIL = "2026-10-12"
DISPLAY_TYPE = "Latest"
LIMIT_PER_QUERY = 50

QUERIES = {
    "politics": [
        "Donald Tusk",
        "Nawrocki",
        "Polska Ukraina",
    ],
    "sport": [
        "Lewandowski",
        "Iga Świątek",
        "Formuła 1",
    ],
    "pop_culture": [
        "Taco Hemingway",
        "Sanah",
        "Friz",
    ],
}


def main() -> None:
    """Collect and save a multidomain sample."""
    auth_token = os.environ.get(AUTH_TOKEN_ENV)

    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell before running this script"
        )

    scraper = Scweet(auth_token=auth_token)

    # tweet_id -> record + information about which searches found it
    collected: dict[str, dict[str, Any]] = {}

    query_results: list[dict[str, Any]] = []

    for domain, queries in QUERIES.items():
        for query in queries:
            print()
            print(f"[{domain}] Searching: {query!r}")

            try:
                records = scraper.search(
                    query,
                    since=SINCE,
                    until=UNTIL,
                    display_type=DISPLAY_TYPE,
                    limit=LIMIT_PER_QUERY,
                )
            except Exception as exc:
                print(f"  Search failed: {exc}")

                query_results.append(
                    {
                        "domain": domain,
                        "query": query,
                        "status": "failed",
                        "error": str(exc),
                        "returned_records": 0,
                    }
                )
                continue

            print(f"  Received {len(records)} records.")

            query_results.append(
                {
                    "domain": domain,
                    "query": query,
                    "status": "ok",
                    "returned_records": len(records),
                }
            )

            for record in records:
                tweet_id = record.get("tweet_id")

                if not tweet_id:
                    continue

                tweet_id = str(tweet_id)

                if tweet_id not in collected:
                    collected[tweet_id] = {
                        "record": record,
                        "sampling_sources": [],
                    }

                source = {
                    "domain": domain,
                    "query": query,
                }

                if source not in collected[tweet_id]["sampling_sources"]:
                    collected[tweet_id]["sampling_sources"].append(source)

    records_output = []

    for tweet_id, item in collected.items():
        records_output.append(
            {
                "tweet_id": tweet_id,
                "sampling_sources": item["sampling_sources"],
                "record": item["record"],
            }
        )

    output = {
        "metadata": {
            "experiment": "multidomain_sample",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "since": SINCE,
            "until": UNTIL,
            "display_type": DISPLAY_TYPE,
            "limit_per_query": LIMIT_PER_QUERY,
            "queries": QUERIES,
            "important_note": (
                "Sampling domain is not the final classification of a post."
            ),
        },
        "query_results": query_results,
        "records": records_output,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print()
    print("=== COLLECTION FINISHED ===")
    print(f"Successful/failed searches: {len(query_results)}")
    print(f"Unique posts: {len(collected)}")
    print(f"Saved dataset to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()