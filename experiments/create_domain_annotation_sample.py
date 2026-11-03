"""Create a reproducible stratified domain annotation sample."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any

from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "domain_annotation_sample.csv"

BATCHES = {
    "batch_1": PROJECT_ROOT / "data" / "scweet_large_sample.json",
    "batch_2": (
        PROJECT_ROOT
        / "data"
        / "scweet_large_sample_2026-10-14_2026-10-20.json"
    ),
}

QUOTAS = {
    "politics": 40,
    "sport": 30,
    "pop_culture": 30,
}

RANDOM_SEED = 42


def load_records(path: Path) -> list[dict[str, Any]]:
    """Load collected Search seed records."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["records"]


def main() -> None:
    """Generate a stratified sample for manual domain annotation."""
    rng = random.Random(RANDOM_SEED)
    mapper = ScweetPostMapper()
    rows: list[dict[str, str]] = []

    for batch_name, path in BATCHES.items():
        records = load_records(path)
        selected_ids: set[str] = set()

        for domain, quota in QUOTAS.items():
            candidates = [
                record
                for record in records
                if domain
                in {
                    source["domain"]
                    for source in record.get("sampling_sources", [])
                }
                and str(record["tweet_id"]) not in selected_ids
            ]

            if len(candidates) < quota:
                raise RuntimeError(
                    f"Not enough candidates for {batch_name}/{domain}"
                )

            selected = rng.sample(candidates, quota)

            for record in selected:
                post = mapper.map_seed(record)
                selected_ids.add(post.post_id)

                sources = record.get("sampling_sources", [])

                rows.append(
                    {
                        "post_id": post.post_id,
                        "batch": batch_name,
                        "sampling_stratum": domain,
                        "sampling_domains": "|".join(
                            sorted({s["domain"] for s in sources})
                        ),
                        "sampling_queries": "|".join(
                            sorted({s["query"] for s in sources})
                        ),
                        "text": post.text,
                        "politics": "",
                        "sport": "",
                        "pop_culture": "",
                        "other": "",
                        "unclear": "",
                        "annotation_notes": "",
                    }
                )

    fieldnames = [
        "post_id",
        "batch",
        "sampling_stratum",
        "sampling_domains",
        "sampling_queries",
        "text",
        "politics",
        "sport",
        "pop_culture",
        "other",
        "unclear",
        "annotation_notes",
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Sample size: {len(rows)}")
    print(f"Unique posts: {len({row['post_id'] for row in rows})}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()