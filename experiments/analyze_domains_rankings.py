
"""Analiza dziedzin i rankingów użytkowników na podstawie danych Scweet."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DOMAINS = ("politics", "sport", "pop_culture")


def run(source: Path, out: Path):
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = payload["records"]
    by_id = {str(x["tweet_id"]): x for x in records}

    items = {}

    for pid, item in by_id.items():
        rec = item["record"]
        raw = rec.get("raw") or {}
        legacy = raw.get("legacy") or {}

        ur = (
            ((raw.get("core") or {}).get("user_results") or {})
            .get("result") or {}
        )
        uc = ur.get("core") or {}
        ul = ur.get("legacy") or {}

        uid = str(
            ur.get("rest_id")
            or ul.get("id_str")
            or (rec.get("user") or {}).get("screen_name")
            or ""
        )

        username = (
            uc.get("screen_name")
            or (rec.get("user") or {}).get("screen_name")
            or uid
        )

        date = legacy.get("created_at") or rec.get("timestamp")
        dt = datetime.strptime(
            date, "%a %b %d %H:%M:%S %z %Y"
        ).astimezone(timezone.utc)

        domains = {
            s["domain"]
            for s in item.get("sampling_sources", [])
            if isinstance(s, dict)
            and s.get("domain") in DOMAINS
        }

        items[pid] = {
            "pid": pid,
            "uid": uid,
            "username": username,
            "date": dt,
            "domains": domains,
            "reply": str(
                legacy.get("in_reply_to_status_id_str") or ""
            ),
            "quote": str(
                legacy.get("quoted_status_id_str") or ""
            ),
            "account_created_at": uc.get("created_at"),
            "likes": int(rec.get("likes") or 0),
            "reposts": int(rec.get("retweets") or 0),
        }

    results = {}
    all_rankings = []

    for domain in ("all",) + DOMAINS:
        scope = {
            pid: post
            for pid, post in items.items()
            if domain == "all" or domain in post["domains"]
        }

        by_user = {}

        def user(uid):
            if uid not in by_user:
                by_user[uid] = {
                    "user_id": uid,
                    "username": "",
                    "account_created_at": None,
                    "post_count": 0,
                    "reply_sent": 0,
                    "quote_sent": 0,
                    "replies_received_in_corpus": 0,
                    "quotes_received_in_corpus": 0,
                    "likes_snapshot_total": 0,
                    "reposts_snapshot_total": 0,
                }
            return by_user[uid]

        missing = Counter()
        refs = Counter()
        edges = Counter()

        for post in scope.values():
            u = user(post["uid"])
            u["username"] = post["username"]
            u["account_created_at"] = (
                post["account_created_at"]
                or u["account_created_at"]
            )

            u["post_count"] += 1
            u["likes_snapshot_total"] += post["likes"]
            u["reposts_snapshot_total"] += post["reposts"]

            for kind in ("reply", "quote"):
                target = post[kind]

                if not target:
                    continue

                refs[kind] += 1
                u[f"{kind}_sent"] += 1

                if target not in scope:
                    missing[kind] += 1
                    continue

                target_user = scope[target]["uid"]

                received_metric = (
                    "replies_received_in_corpus"
                    if kind == "reply"
                    else "quotes_received_in_corpus"
                )

                user(target_user)[received_metric] += 1

                if target_user != post["uid"]:
                    edges[(post["uid"], target_user, kind)] += 1

        rankings = {}

        for metric in (
            "post_count",
            "replies_received_in_corpus",
            "quotes_received_in_corpus",
            "likes_snapshot_total",
        ):
            sorted_users = sorted(
                by_user.values(),
                key=lambda x: (
                    -x[metric],
                    -x["post_count"],
                    x["user_id"],
                ),
            )

            rankings[metric] = [
                {"rank": i + 1, **v}
                for i, v in enumerate(sorted_users[:10])
                if v[metric] > 0
            ]

            for row in rankings[metric]:
                all_rankings.append({
                    "domain": domain,
                    "ranking_metric": metric,
                    **row,
                })

        dates = [p["date"] for p in scope.values()]

        results[domain] = {
            "post_count": len(scope),
            "author_count": len(by_user),
            "published_at_min": (
                min(dates).isoformat() if dates else None
            ),
            "published_at_max": (
                max(dates).isoformat() if dates else None
            ),
            "observed_publication_span_hours": (
                round(
                    (max(dates) - min(dates)).total_seconds() / 3600,
                    3,
                )
                if dates else None
            ),
            "reply_references": refs["reply"],
            "quote_references": refs["quote"],
            "missing_reply_targets": missing["reply"],
            "missing_quote_targets": missing["quote"],
            "in_scope_reply_edges": (
                refs["reply"] - missing["reply"]
            ),
            "in_scope_quote_edges": (
                refs["quote"] - missing["quote"]
            ),
            "unique_user_interaction_edges": len(edges),
            "rankings": rankings,
        }

    out.mkdir(parents=True, exist_ok=True)

    report = {
        "methodology": {
            "cohort": "Publication timestamps within weekly corpus",
            "equal_24h_engagement_snapshots_available": False,
            "snapshot_counter_warning": (
                "Likes and reposts are not verified "
                "24-hour engagement measurements."
            ),
            "ranking_warning": (
                "Received interactions count only targets "
                "available within the same domain subset."
            ),
            "domain_warning": (
                "Sampling domain is not verified "
                "content classification."
            ),
            "pagerank_warning": (
                "PageRank is not calculated by this script."
            ),
        },
        "domains": results,
    }

    (out / "domain_rankings_week3.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fields = [
        "domain",
        "ranking_metric",
        "rank",
        "user_id",
        "username",
        "account_created_at",
        "post_count",
        "reply_sent",
        "quote_sent",
        "replies_received_in_corpus",
        "quotes_received_in_corpus",
        "likes_snapshot_total",
        "reposts_snapshot_total",
    ]

    with (out / "domain_rankings_week3.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_rankings)

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)

    args = parser.parse_args()
    report = run(args.source, args.out)

    for domain, result in report["domains"].items():
        print(
            domain,
            "posts:", result["post_count"],
            "authors:", result["author_count"],
            "replies:", result["in_scope_reply_edges"],
            "quotes:", result["in_scope_quote_edges"],
        )

        for user_data in result["rankings"]["post_count"][:3]:
            print(
                "  TOP:",
                user_data["username"],
                user_data["post_count"],
            )
