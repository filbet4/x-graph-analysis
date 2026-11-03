"""Preview posts for content-domain classification."""

from __future__ import annotations

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "scweet_large_sample.json"

SAMPLE_SIZE = 10
RANDOM_SEED = 42


def load_records() -> list[dict[str, Any]]:
    """Load Search seed records."""
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return data["records"]


def main() -> None:
    """Print a reproducible sample grouped by sampling domain."""
    random.seed(RANDOM_SEED)

    records_by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for item in load_records():
        domains = {
            source["domain"]
            for source in item.get("sampling_sources", [])
            if source.get("domain")
        }

        for domain in domains:
            records_by_domain[domain].append(item)

    for domain in sorted(records_by_domain):
        records = records_by_domain[domain]
        sample = random.sample(
            records,
            min(SAMPLE_SIZE, len(records)),
        )

        print()
        print("=" * 80)
        print(f"SAMPLING DOMAIN: {domain}")
        print(f"AVAILABLE: {len(records)}")
        print("=" * 80)

        for index, item in enumerate(sample, start=1):
            record = item["record"]
            sources = item.get("sampling_sources", [])

            print()
            print(f"[{index}] ID: {item['tweet_id']}")
            print(
                "Queries:",
                [source["query"] for source in sources],
            )
            print("Text:")
            print(record.get("text", "").replace("\n", " "))


if __name__ == "__main__":
    main()