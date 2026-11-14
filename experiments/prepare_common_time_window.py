
import json
from datetime import datetime, timezone
from pathlib import Path

from compare_graph_variants import load_posts


SOURCES = {
    "week1": Path("data/scweet_large_sample.json"),
    "week2": Path(
        "data/scweet_large_sample_2026-10-14_2026-10-20.json"
    ),
    "week3": Path(
        "data/scweet_large_sample_2026-10-21_2026-10-27.json"
    ),
}

OUTPUT_DIR = Path("data/common_time_window")


def to_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("Timestamp without timezone")
    return value.astimezone(timezone.utc)


def main() -> None:
    datasets = {}
    durations = []

    # 1. Load datasets and determine observed time spans.
    for week, path in SOURCES.items():
        with path.open("r", encoding="utf-8") as file:
            raw = json.load(file)

        posts_by_id, _ = load_posts(path)

        if not posts_by_id:
            raise ValueError(f"No posts in {path}")

        dates = [
            to_utc(post.published_at)
            for post in posts_by_id.values()
        ]

        t0 = min(dates)
        tn = max(dates)

        datasets[week] = {
            "raw": raw,
            "posts": posts_by_id,
            "t0": t0,
            "tn": tn,
        }

        durations.append(tn - t0)

    # 2. Use the shortest observed span.
    common_duration = min(durations)

    print(
        "Common duration:",
        round(common_duration.total_seconds() / 3600, 4),
        "hours",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 3. Trim records using tweet_id.
    for week, dataset in datasets.items():
        raw = dataset["raw"]
        posts_by_id = dataset["posts"]
        t0 = dataset["t0"]
        cutoff = t0 + common_duration

        records = raw["records"]

        original_ids = [
            str(record["tweet_id"])
            for record in records
        ]

        if len(original_ids) != len(set(original_ids)):
            raise ValueError(f"{week}: duplicate tweet IDs")

        if set(original_ids) != set(posts_by_id):
            raise ValueError(
                f"{week}: raw IDs and mapped post IDs differ"
            )

        retained_ids = {
            post_id
            for post_id, post in posts_by_id.items()
            if t0 <= to_utc(post.published_at) <= cutoff
        }

        kept_records = [
            record
            for record in records
            if str(record["tweet_id"]) in retained_ids
        ]

        if len(kept_records) != len(retained_ids):
            raise ValueError(
                f"{week}: retained record count mismatch"
            )

        output = dict(raw)
        output["records"] = kept_records
        output["time_window_analysis"] = {
            "method": "observed_t0_plus_common_duration",
            "original_t0": t0.isoformat(),
            "original_tn": dataset["tn"].isoformat(),
            "cutoff": cutoff.isoformat(),
            "duration_hours": (
                common_duration.total_seconds() / 3600
            ),
            "original_records": len(records),
            "retained_records": len(kept_records),
            "removed_records": len(records) - len(kept_records),
        }

        target = OUTPUT_DIR / f"{week}.json"

        with target.open("w", encoding="utf-8") as file:
            json.dump(
                output,
                file,
                ensure_ascii=False,
                indent=2,
            )

        print(
            f"{week}: {len(records)} -> "
            f"{len(kept_records)} posts "
            f"(removed {len(records) - len(kept_records)})"
        )
        print(f"  t0: {t0.isoformat()}")
        print(f"  cutoff: {cutoff.isoformat()}")
        print(f"  saved: {target}")


if __name__ == "__main__":
    main()
