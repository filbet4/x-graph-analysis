
"""Test Scweet collection with separate daily search windows."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from Scweet import Scweet

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "scweet_daily_test.json"

QUERY = "Donald Tusk lang:pl"
START = datetime(2026, 10, 7, tzinfo=timezone.utc)
DAYS = 7
LIMIT = 500


def save(data):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main():
    token = os.environ.get("SCWEET_AUTH_TOKEN")
    if not token:
        raise RuntimeError("Missing SCWEET_AUTH_TOKEN")

    scraper = Scweet(auth_token=token)

    if OUTPUT.exists():
        data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    else:
        data = {
            "metadata": {
                "experiment": "daily_collection_test",
                "query": QUERY,
                "start": START.date().isoformat(),
                "days": DAYS,
                "limit_per_day": LIMIT,
            },
            "query_results": [],
            "records": [],
        }

    existing = {
        str(item["tweet_id"]): item
        for item in data["records"]
        if item.get("tweet_id")
    }

    successful_days = {
        item["since"]
        for item in data["query_results"]
        if item.get("status") == "ok"
    }

    for index in range(DAYS):
        since = (START + timedelta(days=index)).date().isoformat()
        until = (START + timedelta(days=index + 1)).date().isoformat()

        if since in successful_days:
            print(f"Skipping completed day: {since}")
            continue

        print(f"\nCollecting {since} -> {until}")

        try:
            records = scraper.search(
                QUERY,
                since=since,
                until=until,
                display_type="Latest",
                limit=LIMIT,
            )
        except Exception as exc:
            print(f"Failed: {exc}")
            data["query_results"].append({
                "since": since,
                "until": until,
                "status": "failed",
                "error": str(exc),
            })
            save(data)
            continue

        new_posts = 0

        for record in records:
            tweet_id = record.get("tweet_id")
            if not tweet_id:
                continue

            tweet_id = str(tweet_id)

            if tweet_id not in existing:
                existing[tweet_id] = {
                    "tweet_id": tweet_id,
                    "record": record,
                    "sampling_sources": [{
                        "domain": "politics",
                        "query": QUERY,
                    }],
                }
                new_posts += 1

        data["records"] = list(existing.values())
        data["query_results"].append({
            "since": since,
            "until": until,
            "status": "ok",
            "returned_records": len(records),
            "new_unique_posts": new_posts,
        })

        save(data)

        print(f"Returned: {len(records)}")
        print(f"New unique posts: {new_posts}")
        print(f"Total unique posts: {len(existing)}")

    print(f"\nSaved to: {OUTPUT}")


if __name__ == "__main__":
    main()
