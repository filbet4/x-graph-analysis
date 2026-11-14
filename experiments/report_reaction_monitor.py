"""Generate a table and SVG chart from reaction monitor JSONL history."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from statistics import mean, median
from typing import Any

METRICS = (
    "like_count",
    "reply_count",
    "repost_count",
    "quote_count",
    "view_count",
)
OBSERVATION_AGES = (0, 6, 12, 24, 48)


def load_successful_events(path: Path) -> list[dict[str, Any]]:
    """Load only successful observations from append-only history."""
    events: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "observation" and event.get("status") == "ok":
                events.append(event)
    return events


def load_events(path: Path) -> list[dict[str, Any]]:
    """Load all valid monitor events, including skipped and failed slots."""
    events: list[dict[str, Any]] = []
    if not path.exists():
        return events
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") == "observation":
                events.append(event)
    return events


def load_post_ids(path: Path) -> set[str]:
    """Load unique post IDs from the collector JSONL queue."""
    if not path.exists():
        return set()
    post_ids: set[str] = set()
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type", "post") == "post" and event.get("post_id"):
                post_ids.add(str(event["post_id"]))
    return post_ids


def count_rejections(path: Path) -> int:
    """Count collector rejection and query-error events."""
    if not path.exists():
        return 0
    count = 0
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_type") in {"rejected", "query_error"}:
                count += 1
    return count


def write_csv(events: list[dict[str, Any]], path: Path) -> None:
    """Write one row per successful post-age observation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = (
        "post_id",
        "published_at",
        "observed_at",
        "scheduled_age_hours",
        "actual_age_hours",
        *METRICS,
        "missing_metrics",
    )
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        for event in events:
            metrics = event.get("metrics", {})
            writer.writerow(
                {
                    **{field: event.get(field) for field in fields[:5]},
                    **{metric: metrics.get(metric) for metric in METRICS},
                    "missing_metrics": ",".join(event.get("missing_metrics", [])),
                }
            )


def aggregate(events: list[dict[str, Any]]) -> dict[int, dict[str, float | None]]:
    """Calculate per-slot means while ignoring unavailable counters."""
    values: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        age = int(event["scheduled_age_hours"])
        metrics = event.get("metrics", {})
        for metric in METRICS:
            value = metrics.get(metric)
            if isinstance(value, int) and not isinstance(value, bool):
                values[age][metric].append(value)
    return {
        age: {
            metric: (mean(metric_values) if metric_values else None)
            for metric, metric_values in grouped.items()
        }
        for age, grouped in values.items()
    }


def summarize(
    events: Iterable[dict[str, Any]],
    *,
    qualified_post_ids: set[str] | None = None,
    rejected_count: int = 0,
) -> dict[str, Any]:
    """Summarize status, coverage, means, and medians without imputing values."""
    events = list(events)
    status_counts = Counter(str(event.get("status", "unknown")) for event in events)
    successful = [event for event in events if event.get("status") == "ok"]
    slots_by_post: dict[str, set[int]] = defaultdict(set)
    for event in successful:
        post_id = event.get("post_id")
        if post_id:
            slots_by_post[str(post_id)].add(int(event["scheduled_age_hours"]))
    complete_posts = sum(
        set(OBSERVATION_AGES).issubset(slots) for slots in slots_by_post.values()
    )
    distributions: dict[str, dict[str, float | None]] = {}
    for age in OBSERVATION_AGES:
        for metric in METRICS:
            values = [
                int(event["metrics"][metric])
                for event in successful
                if int(event["scheduled_age_hours"]) == age
                and isinstance(event.get("metrics", {}).get(metric), int)
                and not isinstance(event["metrics"][metric], bool)
            ]
            distributions[f"{age}h.{metric}"] = {
                "mean": mean(values) if values else None,
                "median": median(values) if values else None,
            }
    return {
        "qualified_posts": len(qualified_post_ids or set()),
        "rejected_records": rejected_count,
        "observed_posts": len(slots_by_post),
        "complete_posts": complete_posts,
        "status_counts": dict(status_counts),
        "reaction_distributions": distributions,
    }


def write_svg(summary: dict[int, dict[str, float | None]], path: Path) -> None:
    """Write a dependency-free SVG line chart of mean reaction counts."""
    width, height = 960, 540
    left, top, chart_width, chart_height = 80, 40, 820, 410
    ages = sorted(summary)
    points = [
        left + index * chart_width / max(len(ages) - 1, 1) for index in range(len(ages))
    ]
    available = [
        value for row in summary.values() for value in row.values() if value is not None
    ]
    maximum = max(available, default=1.0)
    maximum = maximum or 1.0
    colors = {
        "like_count": "#d95f02",
        "reply_count": "#1b9e77",
        "repost_count": "#7570b3",
        "quote_count": "#e7298a",
        "view_count": "#66a61e",
    }
    lines = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
        ),
        '<rect width="100%" height="100%" fill="white"/>',
        (
            '<text x="80" y="24" font-family="sans-serif" '
            'font-size="18">Mean reactions by post age</text>'
        ),
        (
            f'<line x1="{left}" y1="{top + chart_height}" '
            f'x2="{left + chart_width}" y2="{top + chart_height}" '
            'stroke="#444"/>'
        ),
        (
            f'<line x1="{left}" y1="{top}" x2="{left}" '
            f'y2="{top + chart_height}" stroke="#444"/>'
        ),
    ]
    for index, age in enumerate(ages):
        x = points[index]
        lines.append(
            f'<text x="{x:.1f}" y="480" text-anchor="middle" '
            f'font-family="sans-serif" font-size="12">{age}h</text>'
        )
    for metric, color in colors.items():
        coordinates: list[str] = []
        for index, age in enumerate(ages):
            value = summary[age].get(metric)
            if value is None:
                continue
            x = points[index]
            y = top + chart_height - (float(value) / maximum) * chart_height
            coordinates.append(f"{x:.1f},{y:.1f}")
        if coordinates:
            lines.append(
                f'<polyline points="{" ".join(coordinates)}" fill="none" '
                f'stroke="{color}" stroke-width="2"/>'
            )
            lines.append(
                f'<text x="720" y="{70 + list(colors).index(metric) * 20}" '
                f'font-family="sans-serif" font-size="12" fill="{color}">'
                f"{metric}</text>"
            )
    lines.append("</svg>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    """Generate CSV and SVG outputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--queue", type=Path)
    parser.add_argument("--rejections", type=Path)
    args = parser.parse_args()
    all_events = load_events(args.history)
    successful_events = [event for event in all_events if event.get("status") == "ok"]
    write_csv(successful_events, args.csv)
    write_svg(aggregate(successful_events), args.svg)
    summary = summarize(
        all_events,
        qualified_post_ids=load_post_ids(args.queue) if args.queue else None,
        rejected_count=count_rejections(args.rejections) if args.rejections else 0,
    )
    print(
        json.dumps(
            {
                "observations": len(successful_events),
                "csv": str(args.csv),
                "svg": str(args.svg),
                "summary": summary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
