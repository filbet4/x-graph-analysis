
"""Exploratory account-behavior analysis for a Scweet weekly corpus.

No bot labels or definitive bot scores are produced. No external services used.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DOMAINS = ("politics", "sport", "pop_culture")
DATE_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, DATE_FORMAT).astimezone(timezone.utc)
    except (ValueError, TypeError):
        try:
            return datetime.fromisoformat(
                str(value).replace("Z", "+00:00")
            ).astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None


def normalize(text):
    text = re.sub(r"https?://\S+", " ", text or "", flags=re.I)
    text = re.sub(r"@\w+", " ", text)
    return re.sub(r"\s+", " ", text.casefold()).strip()


def run(source: Path, output: Path):
    data = json.loads(source.read_text(encoding="utf-8"))
    accounts = defaultdict(list)

    for item in data["records"]:
        rec = item.get("record") or {}
        raw = rec.get("raw") or {}

        core = (
            ((raw.get("core") or {}).get("user_results") or {})
            .get("result") or {}
        )
        user_core = core.get("core") or {}
        user = rec.get("user") or {}

        uid = str(
            core.get("rest_id")
            or (raw.get("legacy") or {}).get("user_id_str")
            or user.get("screen_name")
            or ""
        ).strip()

        if not uid:
            continue

        timestamp = parse_date(
            rec.get("timestamp")
            or (raw.get("legacy") or {}).get("created_at")
        )

        if not timestamp:
            continue

        domains = {
            s.get("domain")
            for s in item.get("sampling_sources", [])
            if isinstance(s, dict)
        } & set(DOMAINS)

        accounts[uid].append({
            "post_id": str(
                item.get("tweet_id") or rec.get("tweet_id") or ""
            ),
            "username": (
                user_core.get("screen_name")
                or user.get("screen_name")
                or ""
            ),
            "timestamp": timestamp,
            "text": (
                rec.get("text")
                or (raw.get("legacy") or {}).get("full_text")
                or ""
            ),
            "account_created": parse_date(
                user_core.get("created_at")
            ),
            "domains": domains,
        })

    rows = []

    for uid, posts in accounts.items():
        posts.sort(key=lambda p: p["timestamp"])

        dates = [p["timestamp"] for p in posts]

        gaps = [
            (b - a).total_seconds() / 60
            for a, b in zip(dates, dates[1:])
        ]

        texts = [normalize(p["text"]) for p in posts]
        meaningful = [t for t in texts if len(t) >= 20]

        duplicates = sum(
            n - 1
            for n in Counter(meaningful).values()
            if n > 1
        )

        created = next(
            (
                p["account_created"]
                for p in posts
                if p["account_created"]
            ),
            None,
        )

        duration_hours = (
            (dates[-1] - dates[0]).total_seconds() / 3600
            if len(dates) > 1
            else 0
        )

        domain_counts = Counter(
            d for p in posts for d in p["domains"]
        )

        row = {
            "user_id": uid,
            "username": posts[-1]["username"],
            "post_count": len(posts),
            "politics_posts": domain_counts["politics"],
            "sport_posts": domain_counts["sport"],
            "pop_culture_posts": domain_counts["pop_culture"],
            "first_post_utc": dates[0].isoformat(),
            "last_post_utc": dates[-1].isoformat(),
            "active_span_hours": round(duration_hours, 2),
            "max_posts_in_one_utc_hour": max(
                Counter(
                    d.strftime("%Y-%m-%dT%H")
                    for d in dates
                ).values()
            ),
            "median_gap_minutes": (
                round(sorted(gaps)[len(gaps) // 2], 2)
                if gaps else None
            ),
            "gaps_under_2min_pct": (
                round(
                    100 * sum(g < 2 for g in gaps) / len(gaps),
                    2,
                )
                if gaps else None
            ),
            "exact_duplicate_texts": duplicates,
            "exact_duplicate_texts_pct": (
                round(100 * duplicates / len(meaningful), 2)
                if meaningful else None
            ),
            "account_created_utc": (
                created.isoformat() if created else None
            ),
            "account_age_days_at_first_post": (
                (dates[0] - created).days if created else None
            ),
        }

        rows.append(row)

    rows.sort(
        key=lambda r: (-r["post_count"], r["user_id"])
    )

    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "account_behavior_week3.csv"

    with csv_path.open(
        "w", newline="", encoding="utf-8-sig"
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0]) if rows else ["user_id"],
        )
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "post_count": sum(r["post_count"] for r in rows),
        "account_count": len(rows),
        "accounts_with_creation_date": sum(
            r["account_created_utc"] is not None
            for r in rows
        ),
        "accounts_with_at_least_5_posts": sum(
            r["post_count"] >= 5 for r in rows
        ),
        "accounts_with_exact_duplicate_texts": sum(
            r["exact_duplicate_texts"] > 0
            for r in rows
        ),
        "methodology": {
            "observation": (
                "Only posts captured in this weekly sampling corpus, "
                "not complete account timelines."
            ),
            "duplicate_definition": (
                "Exact match after casefolding, URL removal, "
                "mention removal, and whitespace normalization; "
                "texts shorter than 20 characters excluded."
            ),
            "time_window": (
                "Publication timestamps of captured posts; "
                "no verified 24-hour engagement snapshots."
            ),
            "interpretation": (
                "Exploratory behavioral indicators, not bot "
                "identification or a probability of automation."
            ),
            "limitations": (
                "Sampling bias, incomplete account timelines, "
                "cross-posting, news syndication, "
                "missing account metadata."
            ),
        },
    }

    (output / "account_behavior_week3_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("CSV:", csv_path)

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source", type=Path, required=True
    )
    parser.add_argument(
        "--out", type=Path, default=Path("reports")
    )

    args = parser.parse_args()
    run(args.source, args.out)
