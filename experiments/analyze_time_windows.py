
"""Analyze actual publication windows for Scweet datasets."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from compare_graph_variants import DOMAINS, load_posts


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASETS = {
    "week1": PROJECT_ROOT / "data" / "scweet_large_sample.json",
    "week2": (
        PROJECT_ROOT
        / "data"
        / "scweet_large_sample_2026-10-14_2026-10-20.json"
    ),
    "week3": (
        PROJECT_ROOT
        / "data"
        / "scweet_large_sample_2026-10-21_2026-10-27.json"
    ),
}

SCOPES = ("all", *DOMAINS)


def window_stats(timestamps: list[datetime]) -> dict:
    """Calculate actual t0, tn and observation duration."""
    if not timestamps:
        return {
            "post_count": 0,
            "t0": None,
            "tn": None,
            "duration_hours": None,
            "duration_days": None,
        }

    normalized = [
        timestamp.astimezone(UTC)
        for timestamp in timestamps
    ]

    t0 = min(normalized)
    tn = max(normalized)
    duration = (tn - t0).total_seconds()

    return {
        "post_count": len(normalized),
        "t0": t0.isoformat(),
        "tn": tn.isoformat(),
        "duration_hours": round(duration / 3600, 4),
        "duration_days": round(duration / 86400, 4),
    }


def analyze_dataset(week: str, source: Path) -> list[dict]:
    posts, domains = load_posts(source)

    results = []

    for scope in SCOPES:
        selected = [
            post.published_at
            for post_id, post in posts.items()
            if scope == "all" or scope in domains[post_id]
        ]

        results.append({
            "week": week,
            "scope": scope,
            **window_stats(selected),
        })

    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "reports" / "time_windows_weeks1_3.csv",
    )
    args = parser.parse_args()

    rows = []

    for week, source in DATASETS.items():
        if not source.exists():
            raise FileNotFoundError(source)

        rows.extend(analyze_dataset(week, source))

    args.out.parent.mkdir(parents=True, exist_ok=True)

    with args.out.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "week",
                "scope",
                "post_count",
                "t0",
                "tn",
                "duration_hours",
                "duration_days",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print(f"\nSaved report: {args.out}")


if __name__ == "__main__":
    main()
