
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path


def get_id(item: dict) -> str:
    record = item.get("record") or {}
    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    return str(
        item.get("tweet_id")
        or record.get("tweet_id")
        or legacy.get("id_str")
        or ""
    ).strip()


def get_legacy(item: dict) -> dict:
    record = item.get("record") or {}
    raw = record.get("raw") or {}
    return raw.get("legacy") or {}


def is_political(item: dict) -> bool:
    return any(
        isinstance(source, dict)
        and source.get("domain") == "politics"
        for source in item.get("sampling_sources", [])
    )


def load_annotations(path: Path) -> dict[str, dict]:
    result = {}

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        for row in csv.DictReader(file):
            post_id = str(row.get("tweet_id") or "").strip()

            if post_id:
                result[post_id] = row

    return result


def classify_interaction(legacy: dict) -> str:
    reply = legacy.get("in_reply_to_status_id_str")
    quote = legacy.get("quoted_status_id_str")

    if reply and quote:
        return "REPLY_AND_QUOTE"
    if reply:
        return "REPLY"
    if quote:
        return "QUOTE"

    return "OTHER"


def percentage(part: int, total: int) -> float:
    return round(100 * part / total, 2) if total else 0.0


def analyze(source: Path, annotations: Path, out: Path) -> None:
    payload = json.loads(source.read_text(encoding="utf-8"))
    flagged = load_annotations(annotations)

    political = {
        get_id(item): item
        for item in payload["records"]
        if is_political(item) and get_id(item)
    }

    missing = set(flagged) - set(political)

    groups = {
        "flagged": Counter(),
        "other": Counter(),
    }

    rows = []

    for post_id, item in political.items():
        group = "flagged" if post_id in flagged else "other"
        legacy = get_legacy(item)
        interaction = classify_interaction(legacy)

        groups[group][interaction] += 1

        rows.append({
            "tweet_id": post_id,
            "group": group,
            "interaction": interaction,
            "reply_target": str(
                legacy.get("in_reply_to_status_id_str") or ""
            ),
            "quote_target": str(
                legacy.get("quoted_status_id_str") or ""
            ),
            "manual_label": (
                flagged[post_id].get("manual_label", "")
                if post_id in flagged else ""
            ),
        })

    summary = {
        "total_political_posts": len(political),
        "flagged_found": len(set(flagged) & set(political)),
        "flagged_missing": len(missing),
        "groups": {},
    }

    for group, counts in groups.items():
        total = sum(counts.values())
        reply_count = (
            counts["REPLY"] + counts["REPLY_AND_QUOTE"]
        )
        quote_count = (
            counts["QUOTE"] + counts["REPLY_AND_QUOTE"]
        )

        summary["groups"][group] = {
            "total": total,
            "reply_count": reply_count,
            "reply_pct": percentage(reply_count, total),
            "quote_count": quote_count,
            "quote_pct": percentage(quote_count, total),
            "other_count": counts["OTHER"],
            "other_pct": percentage(counts["OTHER"], total),
            "both_reply_and_quote": counts["REPLY_AND_QUOTE"],
        }

    out.mkdir(parents=True, exist_ok=True)

    summary_path = out / "political_interaction_comparison.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    csv_path = out / "political_interaction_comparison.csv"

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "tweet_id",
                "group",
                "interaction",
                "reply_target",
                "quote_target",
                "manual_label",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("\nZapisano:", summary_path)
    print("Zapisano:", csv_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--out", default=Path("reports"), type=Path)

    args = parser.parse_args()

    analyze(args.source, args.annotations, args.out)
