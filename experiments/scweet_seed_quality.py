"""Collect candidate seed posts for query-quality evaluation.

This experiment compares search queries from three domains:
politics, sport and pop culture.

The goal is to evaluate which queries produce:
- Polish-language posts,
- posts actually related to the intended domain,
- useful candidate seeds for later conversation collection.

Search queries are sampling sources only. They do not determine
the final content classification.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Scweet import Scweet


PROJECT_ROOT = Path(__file__).resolve().parents[1]

JSON_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "scweet_seed_quality.json"
)

CSV_OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "scweet_seed_quality.csv"
)

AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"

SINCE = "2026-10-04"
UNTIL = "2026-10-12"
DISPLAY_TYPE = "Latest"

# Scweet may return slightly more records than requested.
LIMIT_PER_QUERY = 25

QUERIES = {
    "politics": [
        "Donald Tusk",
        "Karol Nawrocki",
        "Sejm",
        "PiS",
        "Konfederacja",
    ],
    "sport": [
        "Iga Świątek",
        "Robert Lewandowski",
        "reprezentacja Polski",
        "Ekstraklasa",
        "polska siatkówka",
    ],
    "pop_culture": [
        "Friz Ekipa",
        "Mata",
        "Taco Hemingway",
        "Quebonafide",
        "Bedoes",
    ],
}


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


def main() -> None:
    """Collect candidate seeds and save JSON and annotation CSV."""
    auth_token = os.environ.get(AUTH_TOKEN_ENV)

    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell before running this script"
        )

    scraper = Scweet(auth_token=auth_token)

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
            "experiment": "seed_query_quality",
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "since": SINCE,
            "until": UNTIL,
            "display_type": DISPLAY_TYPE,
            "limit_per_query": LIMIT_PER_QUERY,
            "queries": QUERIES,
            "important_note": (
                "Sampling domain is not the final classification "
                "of a post."
            ),
        },
        "query_results": query_results,
        "records": records_output,
    }

    JSON_OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    JSON_OUTPUT_PATH.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Create a flat CSV for manual inspection.
    csv_rows: list[dict[str, str]] = []

    for tweet_id, item in collected.items():
        record = item["record"]
        text = extract_text(record)

        for source in item["sampling_sources"]:
            csv_rows.append(
                {
                    "tweet_id": tweet_id,
                    "sampling_domain": source["domain"],
                    "query": source["query"],
                    "text": text,
                    "language": "",
                    "relevant": "",
                    "notes": "",
                }
            )

    with CSV_OUTPUT_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "tweet_id",
                "sampling_domain",
                "query",
                "text",
                "language",
                "relevant",
                "notes",
            ],
        )

        writer.writeheader()
        writer.writerows(csv_rows)

    print()
    print("=== SEED QUALITY COLLECTION FINISHED ===")

    print(f"Queries tested: {len(query_results)}")
    print(f"Unique posts: {len(collected)}")
    print(f"CSV rows: {len(csv_rows)}")

    print()
    print("Results per query:")

    for result in query_results:
        status = result["status"]
        count = result["returned_records"]

        print(
            f"  [{result['domain']}] "
            f"{result['query']}: "
            f"{count} ({status})"
        )

    print()
    print(f"Raw JSON: {JSON_OUTPUT_PATH}")
    print(f"Inspection CSV: {CSV_OUTPUT_PATH}")


if __name__ == "__main__":
    main()