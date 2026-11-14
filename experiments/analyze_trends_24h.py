
"""Analyze post popularity and hashtag trends in consecutive 24h windows."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from datetime import UTC, timedelta
from pathlib import Path

from compare_graph_variants import DOMAINS, load_posts

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "common_time_window"
OUTPUT = ROOT / "reports" / "trends_24h"

SOURCES = {
    "week1": DATA / "week1.json",
    "week2": DATA / "week2.json",
    "week3": DATA / "week3.json",
}


def write_csv(filename, rows, fields):
    path = OUTPUT / filename
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {path} ({len(rows)} rows)")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)

    post_rows = []
    hashtag_rows = []
    summary_rows = []

    for week, source in SOURCES.items():
        posts, domains = load_posts(source)
        if not posts:
            continue

        t0 = min(post.published_at.astimezone(UTC) for post in posts.values())
        windows = defaultdict(list)

        for post in posts.values():
            published = post.published_at.astimezone(UTC)
            index = int((published - t0) // timedelta(hours=24))
            windows[index].append(post)

        previous_tags = {}

        for index in sorted(windows):
            group = windows[index]
            start = t0 + timedelta(hours=24 * index)
            end = start + timedelta(hours=24)

            for domain in ("all", *DOMAINS):
                selected = [
                    post for post in group
                    if domain == "all"
                    or domain in domains.get(post.post_id, set())
                ]

                if not selected:
                    continue

                tags = Counter(
                    tag.normalized_text
                    for post in selected
                    for tag in {
                        tag.normalized_text: tag
                        for tag in post.hashtags
                    }.values()
                )

                previous = previous_tags.get(domain, Counter())

                for tag, count in tags.most_common(20):
                    hashtag_rows.append({
                        "week": week,
                        "window": index + 1,
                        "domain": domain,
                        "start_utc": start.isoformat(),
                        "hashtag": tag,
                        "posts_with_hashtag": count,
                        "previous_window_count": previous.get(tag, 0),
                        "change": count - previous.get(tag, 0),
                    })

                previous_tags[domain] = tags

                def engagement(post):
                    m = post.metrics
                    if m is None:
                        return 0
                    return (
                        m.like_count
                        + m.repost_count
                        + m.reply_count
                        + m.quote_count
                    )

                ranked = sorted(
                    selected,
                    key=lambda p: (-engagement(p), p.post_id),
                )

                for rank, post in enumerate(ranked[:20], start=1):
                    m = post.metrics
                    post_rows.append({
                        "week": week,
                        "window": index + 1,
                        "domain": domain,
                        "rank": rank,
                        "post_id": post.post_id,
                        "username": post.author.username,
                        "published_at_utc": post.published_at.isoformat(),
                        "likes_snapshot": m.like_count if m else 0,
                        "reposts_snapshot": m.repost_count if m else 0,
                        "replies_snapshot": m.reply_count if m else 0,
                        "quotes_snapshot": m.quote_count if m else 0,
                        "engagement_snapshot_sum": engagement(post),
                        "text": post.text[:500].replace("\n", " "),
                        "url": (
                            f"https://x.com/{post.author.username}/"
                            f"status/{post.post_id}"
                        ),
                    })

                summary_rows.append({
                    "week": week,
                    "window": index + 1,
                    "domain": domain,
                    "start_utc": start.isoformat(),
                    "end_utc_exclusive": end.isoformat(),
                    "post_count": len(selected),
                    "unique_authors": len({
                        post.author.user_id for post in selected
                    }),
                    "total_likes_snapshot": sum(
                        p.metrics.like_count if p.metrics else 0
                        for p in selected
                    ),
                    "total_reposts_snapshot": sum(
                        p.metrics.repost_count if p.metrics else 0
                        for p in selected
                    ),
                    "distinct_hashtags": len(tags),
                })

    write_csv(
        "trends_24h_posts.csv",
        post_rows,
        [
            "week", "window", "domain", "rank", "post_id",
            "username", "published_at_utc", "likes_snapshot",
            "reposts_snapshot", "replies_snapshot",
            "quotes_snapshot", "engagement_snapshot_sum",
            "text", "url",
        ],
    )

    write_csv(
        "trends_24h_hashtags.csv",
        hashtag_rows,
        [
            "week", "window", "domain", "start_utc",
            "hashtag", "posts_with_hashtag",
            "previous_window_count", "change",
        ],
    )

    write_csv(
        "trends_24h_summary.csv",
        summary_rows,
        [
            "week", "window", "domain", "start_utc",
            "end_utc_exclusive", "post_count",
            "unique_authors", "total_likes_snapshot",
            "total_reposts_snapshot", "distinct_hashtags",
        ],
    )


if __name__ == "__main__":
    main()
