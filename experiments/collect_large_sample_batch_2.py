"""Collect a large multidomain Scweet dataset for model design.

The collector retrieves X posts related to three broad sampling domains:
politics, sport and pop culture.

Search queries are sampling sources only. They MUST NOT be interpreted as
the final domain classification of a post.

The collector is resumable:
- previously collected posts are loaded from disk,
- successfully completed queries are skipped,
- failed queries can be retried in later runs,
- results are deduplicated by tweet_id,
- progress is saved after every query.
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
    / "scweet_large_sample_2026-10-14_2026-10-20.json"
)

CHECKPOINT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_large_sample_2026-10-14_2026-10-20_checkpoint.json"
)
AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"
SINCE = "2026-10-14"
UNTIL = "2026-10-21"

DISPLAY_TYPE = "Latest"

# Scweet does not necessarily treat this as an exact number
# of returned posts.
LIMIT_PER_QUERY = 500


QUERIES = {
    "politics": [
        "Donald Tusk lang:pl",
        "Karol Nawrocki lang:pl",
        "Prawo i Sprawiedliwość lang:pl",
        "Konfederacja lang:pl",
        "Sejm lang:pl",
    ],
    "sport": [
        "Iga Świątek lang:pl",
        "Robert Lewandowski lang:pl",
        "reprezentacja Polski lang:pl",
        "Ekstraklasa lang:pl",
        "polska siatkówka lang:pl",
    ],
    "pop_culture": [
        "Friz Ekipa lang:pl",
        "Mata raper lang:pl",
        "Taco Hemingway lang:pl",
        "Quebonafide lang:pl",
        "Bedoes lang:pl",
        "polski rap lang:pl",
        "FAME MMA lang:pl",
    ],
}


def load_existing_dataset() -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
]:
    """Load previously collected posts and query history."""

    # Prefer the final dataset from a previous run.
    # If it does not exist, try the checkpoint.
    if OUTPUT_PATH.exists():
        path = OUTPUT_PATH
    elif CHECKPOINT_PATH.exists():
        path = CHECKPOINT_PATH
    else:
        return {}, []

    print(f"Loading existing dataset: {path}")

    data = json.loads(
        path.read_text(encoding="utf-8")
    )

    collected: dict[str, dict[str, Any]] = {}

    for item in data.get("records", []):
        tweet_id = item.get("tweet_id")

        if not tweet_id:
            continue

        tweet_id = str(tweet_id)

        collected[tweet_id] = {
            "record": item["record"],
            "sampling_sources": item.get(
                "sampling_sources",
                [],
            ),
        }

    query_results = data.get("query_results", [])

    return collected, query_results


def save_dataset(
    path: Path,
    collected: dict[str, dict[str, Any]],
    query_results: list[dict[str, Any]],
    *,
    status: str,
) -> None:
    """Save the current collection state."""

    records_output = []

    for tweet_id, item in collected.items():
        records_output.append(
            {
                "tweet_id": tweet_id,
                "sampling_sources": item["sampling_sources"],
                "record": item["record"],
            }
        )

    successful_queries = {
        (result["domain"], result["query"])
        for result in query_results
        if result.get("status") == "ok"
    }

    output = {
        "metadata": {
            "experiment": "large_multidomain_sample",
            "collection_status": status,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "since": SINCE,
            "until": UNTIL,
            "display_type": DISPLAY_TYPE,
            "limit_per_query": LIMIT_PER_QUERY,
            "queries": QUERIES,
            "unique_posts": len(collected),
            "completed_queries": len(successful_queries),
            "total_queries": sum(
                len(queries)
                for queries in QUERIES.values()
            ),
            "important_note": (
                "Sampling domain and query describe how a post was found. "
                "They are not the final content or author classification."
            ),
        },
        "query_results": query_results,
        "records": records_output,
    }

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    """Collect and save a large multidomain sample."""

    auth_token = os.environ.get(AUTH_TOKEN_ENV)

    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell "
            "before running this script"
        )

    collected, query_results = load_existing_dataset()

    # A query is considered completed if it succeeded at least once.
    successful_queries = {
        (result["domain"], result["query"])
        for result in query_results
        if result.get("status") == "ok"
    }

    total_queries = sum(
        len(queries)
        for queries in QUERIES.values()
    )

    print()
    print("=" * 70)
    print("RESUMABLE LARGE SAMPLE COLLECTION")
    print("=" * 70)
    print(f"Existing unique posts: {len(collected)}")
    print(
        f"Already completed queries: "
        f"{len(successful_queries)}/{total_queries}"
    )
    print(f"Collection window: {SINCE} -> {UNTIL}")
    print()

    scraper = Scweet(auth_token=auth_token)

    query_number = 0

    for domain, queries in QUERIES.items():
        for query in queries:
            query_number += 1

            # Do not repeat searches which already completed successfully.
            if (domain, query) in successful_queries:
                print(
                    f"[{query_number}/{total_queries}] "
                    f"Skipping completed query: {query!r}"
                )
                continue

            print()
            print("=" * 70)
            print(f"[{query_number}/{total_queries}]")
            print(f"Domain: {domain}")
            print(f"Query: {query!r}")
            print("=" * 70)

            started_at = datetime.now(timezone.utc)

            try:
                records = scraper.search(
                    query,
                    since=SINCE,
                    until=UNTIL,
                    display_type=DISPLAY_TYPE,
                    limit=LIMIT_PER_QUERY,
                )

            except Exception as exc:
                finished_at = datetime.now(timezone.utc)

                print(f"Search failed: {exc}")

                query_results.append(
                    {
                        "domain": domain,
                        "query": query,
                        "status": "failed",
                        "error": str(exc),
                        "returned_records": 0,
                        "started_at": started_at.isoformat(),
                        "finished_at": finished_at.isoformat(),
                    }
                )

                # Save immediately even after a failure.
                save_dataset(
                    CHECKPOINT_PATH,
                    collected,
                    query_results,
                    status="in_progress",
                )

                continue

            finished_at = datetime.now(timezone.utc)

            print(f"Received {len(records)} records.")

            new_unique_posts = 0
            duplicate_posts = 0
            records_without_id = 0

            for record in records:
                tweet_id = record.get("tweet_id")

                if not tweet_id:
                    records_without_id += 1
                    continue

                tweet_id = str(tweet_id)

                if tweet_id not in collected:
                    collected[tweet_id] = {
                        "record": record,
                        "sampling_sources": [],
                    }

                    new_unique_posts += 1

                else:
                    duplicate_posts += 1

                source = {
                    "domain": domain,
                    "query": query,
                }

                if (
                    source
                    not in collected[tweet_id]["sampling_sources"]
                ):
                    collected[tweet_id][
                        "sampling_sources"
                    ].append(source)

            query_results.append(
                {
                    "domain": domain,
                    "query": query,
                    "status": "ok",
                    "returned_records": len(records),
                    "new_unique_posts": new_unique_posts,
                    "duplicates": duplicate_posts,
                    "records_without_id": records_without_id,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                }
            )

            successful_queries.add(
                (domain, query)
            )

            print(f"New unique posts: {new_unique_posts}")
            print(f"Duplicates: {duplicate_posts}")

            if records_without_id:
                print(
                    f"Records without tweet_id: "
                    f"{records_without_id}"
                )

            print(
                f"Total unique posts so far: "
                f"{len(collected)}"
            )

            # Save after every successful query.
            save_dataset(
                CHECKPOINT_PATH,
                collected,
                query_results,
                status="in_progress",
            )

    completed_queries = len(successful_queries)

    if completed_queries == total_queries:
        collection_status = "finished"
    else:
        collection_status = "partial"

    # Always save the current state to the main dataset as well.
    save_dataset(
        OUTPUT_PATH,
        collected,
        query_results,
        status=collection_status,
    )

    print()
    print("=" * 70)
    print("COLLECTION RUN FINISHED")
    print("=" * 70)
    print(
        f"Completed queries: "
        f"{completed_queries}/{total_queries}"
    )
    print(
        f"Remaining queries: "
        f"{total_queries - completed_queries}"
    )
    print(f"Unique posts: {len(collected)}")
    print(f"Status: {collection_status}")
    print()
    print(f"Dataset: {OUTPUT_PATH}")
    print(f"Checkpoint: {CHECKPOINT_PATH}")

    if completed_queries < total_queries:
        print()
        print(
            "Some queries are still incomplete. "
            "Run this script again later to retry only "
            "the unfinished queries."
        )


if __name__ == "__main__":
    main()