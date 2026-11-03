"""Preview candidate seed posts grouped by search query."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_seed_quality.csv"
)

PREVIEW_PER_QUERY = 8


def shorten(text: str, limit: int = 280) -> str:
    """Make long tweet text easier to inspect in the terminal."""
    text = " ".join(text.split())

    if len(text) <= limit:
        return text

    return text[: limit - 3] + "..."


def main() -> None:
    with INPUT_PATH.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    grouped: dict[
        tuple[str, str],
        list[dict[str, str]],
    ] = defaultdict(list)

    for row in rows:
        key = (
            row["sampling_domain"],
            row["query"],
        )
        grouped[key].append(row)

    print("=== SEED QUALITY PREVIEW ===")
    print(f"CSV rows: {len(rows)}")
    print()

    for (domain, query), query_rows in grouped.items():
        print("=" * 80)
        print(f"DOMAIN: {domain}")
        print(f"QUERY:  {query}")
        print(f"POSTS:  {len(query_rows)}")
        print("=" * 80)

        for index, row in enumerate(
            query_rows[:PREVIEW_PER_QUERY],
            start=1,
        ):
            print()
            print(f"[{index}] {row['tweet_id']}")
            print(shorten(row["text"]))

        print()

    print("=== END OF PREVIEW ===")


if __name__ == "__main__":
    main()