"""Test retrieval of missing quote targets by tweet ID.

The experiment searches existing collected datasets for quoted tweets
that are not present as main records in the same dataset and attempts
to retrieve them using Scweet.get_tweet_info().
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Scweet import Scweet


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

OUTPUT_PATH = DATA_DIR / "scweet_target_retrieval_test.json"

AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"

MAX_TARGETS = 10


def get_tweet_id(record: dict[str, Any]) -> str | None:
    """Return normalized tweet ID."""
    value = record.get("tweet_id")

    if value is None:
        return None

    value = str(value).strip()

    return value or None


def find_quoted_status_id(value: Any) -> str | None:
    """Recursively search raw X data for quoted_status_id_str."""

    if isinstance(value, dict):
        quoted_id = value.get("quoted_status_id_str")

        if quoted_id:
            return str(quoted_id)

        for child in value.values():
            result = find_quoted_status_id(child)

            if result:
                return result

    elif isinstance(value, list):
        for child in value:
            result = find_quoted_status_id(child)

            if result:
                return result

    return None


def get_quote_target(record: dict[str, Any]) -> str | None:
    """Extract quoted tweet ID from known Scweet record variants."""

    # Preferred source: normalized Scweet field.
    quoted_tweet = record.get("quoted_tweet")

    if isinstance(quoted_tweet, dict):
        value = quoted_tweet.get("tweet_id")

        if value:
            return str(value)

    # Fallback: raw X/GraphQL payload.
    raw = record.get("raw")

    if isinstance(raw, dict):
        return find_quoted_status_id(raw)

    return None


def get_main_records(
    data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return only main tweet records from a collected dataset."""

    items = data.get("records")

    if not isinstance(items, list):
        return []

    records: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        record = item.get("record")

        if isinstance(record, dict):
            records.append(record)

    return records


def collect_missing_quote_targets() -> list[dict[str, str]]:
    """Find quote targets missing from existing datasets."""

    candidates: list[dict[str, str]] = []
    seen_targets: set[str] = set()

    ignored_files = {
        OUTPUT_PATH.name,
        "scweet_language_filter_test.json",
        "scweet_seed_quality.json",
    }

    for path in sorted(DATA_DIR.glob("*.json")):
        if path.name in ignored_files:
            continue

        try:
            data = json.loads(
                path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            continue

        if not isinstance(data, dict):
            continue

        records = get_main_records(data)

        if not records:
            continue

        existing_ids = {
            tweet_id
            for record in records
            if (tweet_id := get_tweet_id(record))
        }

        for record in records:
            source_id = get_tweet_id(record)
            target_id = get_quote_target(record)

            if not source_id or not target_id:
                continue

            if target_id in existing_ids:
                continue

            if target_id in seen_targets:
                continue

            seen_targets.add(target_id)

            candidates.append(
                {
                    "source_file": path.name,
                    "source_tweet_id": source_id,
                    "relationship": "QUOTE",
                    "target_tweet_id": target_id,
                }
            )

            if len(candidates) >= MAX_TARGETS:
                return candidates

    return candidates


def main() -> None:
    """Run missing quote target retrieval experiment."""

    auth_token = os.environ.get(AUTH_TOKEN_ENV)

    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} before running the experiment"
        )

    targets = collect_missing_quote_targets()

    print()
    print("=" * 80)
    print("SCWEET TARGET RETRIEVAL TEST")
    print("=" * 80)
    print(f"Missing quote targets found: {len(targets)}")

    if not targets:
        print(
            "No missing quote targets were found in existing JSON files."
        )
        return

    for index, target in enumerate(targets, start=1):
        print(
            f"{index:2}. "
            f"{target['source_tweet_id']} "
            f"--QUOTE--> "
            f"{target['target_tweet_id']} "
            f"[{target['source_file']}]"
        )

    target_ids = [
        target["target_tweet_id"]
        for target in targets
    ]

    print()
    print("Requesting targets using get_tweet_info()...")
    print()

    scraper = Scweet(auth_token=auth_token)

    try:
        retrieved = scraper.get_tweet_info(target_ids)
    except Exception as exc:
        print(f"Request failed: {exc}")
        return

    retrieved_by_id = {
        str(record["tweet_id"]): record
        for record in retrieved
        if isinstance(record, dict) and record.get("tweet_id")
    }

    results: list[dict[str, Any]] = []

    print("=" * 80)
    print("RESULTS")
    print("=" * 80)

    for target in targets:
        target_id = target["target_tweet_id"]
        record = retrieved_by_id.get(target_id)

        success = record is not None

        result = {
            **target,
            "retrieved": success,
            "record": record,
        }

        results.append(result)

        status = "OK" if success else "MISSING"

        print(
            f"{status:7} | "
            f"{target['source_tweet_id']} "
            f"--QUOTE--> "
            f"{target_id}"
        )

    successful = sum(
        1
        for result in results
        if result["retrieved"]
    )

    total = len(results)

    success_rate = (
        successful / total * 100
        if total
        else 0.0
    )

    output = {
        "metadata": {
            "experiment": "target_retrieval_test",
            "collected_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "max_targets": MAX_TARGETS,
            "relationship": "QUOTE",
            "method": "Scweet.get_tweet_info",
        },
        "summary": {
            "tested": total,
            "retrieved": successful,
            "missing": total - successful,
            "success_rate_percent": round(
                success_rate,
                1,
            ),
        },
        "results": results,
    }

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
    print("SUMMARY")
    print("=" * 80)
    print(f"Tested:       {total}")
    print(f"Retrieved:    {successful}")
    print(f"Missing:      {total - successful}")
    print(f"Success rate: {success_rate:.1f}%")
    print()
    print(f"Saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()