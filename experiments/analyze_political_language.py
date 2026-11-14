"""Exploratory, auditable screening of potentially abusive political posts.

Does not classify posts as hate speech. Outputs candidates for human review.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

# Small, deliberately conservative starting lexicon; edit after manual review.
PATTERNS = {
    "direct_insult": [r"\bidiot(?:a|ą|o|y|ów|ami)?\b", r"\bdeb il\b".replace(" ", ""),
                      r"\bkretyn(?:a|ie|em|i|ów)?\b", r"\bimbecyl(?:a|e|u|i)?\b",
                      r"\bbaran(?:ie|y|ów)?\b"],
    "profanity": [r"\bkurw\w*\b", r"\bchuj\w*\b", r"\bpierdol\w*\b",
                  r"\bjeba\w*\b", r"\bspierdal\w*\b"],
    "hostile_wish": [r"\b(?:zdechnij|zdychaj|giń|zginiesz)\b"],
}
COMPILED = {k: [re.compile(p, re.I) for p in v] for k, v in PATTERNS.items()}
FIELDS = ["tweet_id", "username", "published_at", "text", "categories",
          "matched_terms", "manual_label", "review_notes"]


def screen(text: str) -> tuple[list[str], list[str]]:
    categories, matches = [], set()
    for category, patterns in COMPILED.items():
        hits = [m.group(0).casefold() for p in patterns for m in p.finditer(text)]
        if hits:
            categories.append(category)
            matches.update(hits)
    return categories, sorted(matches)


def analyze(source: Path, out: Path) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = payload["records"]
    political = []
    candidates = []
    by_category = Counter()
    for item in records:
        domains = {s.get("domain") for s in item.get("sampling_sources", [])
                   if isinstance(s, dict)}
        if "politics" not in domains:
            continue
        rec = item.get("record") or {}
        raw = rec.get("raw") or {}
        text = str(rec.get("text") or (raw.get("legacy") or {}).get("full_text") or "")
        political.append(item)
        categories, terms = screen(text)
        if not categories:
            continue
        by_category.update(categories)
        candidates.append({
            "tweet_id": str(item.get("tweet_id") or rec.get("tweet_id") or ""),
            "username": (rec.get("user") or {}).get("screen_name", ""),
            "published_at": rec.get("timestamp", ""),
            "text": text,
            "categories": ";".join(categories),
            "matched_terms": ";".join(terms),
            "manual_label": "",  # fill after reading: insult / criticism / other / uncertain
            "review_notes": "",
        })
    out.mkdir(parents=True, exist_ok=True)
    candidates.sort(key=lambda x: (x["published_at"], x["tweet_id"]))
    with (out / "political_language_review_week3.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(candidates)
    summary = {
        "political_posts": len(political),
        "flagged_for_manual_review": len(candidates),
        "flagged_share_pct": round(100 * len(candidates) / len(political), 2) if political else 0,
        "category_occurrences": dict(by_category),
        "method": "Conservative regex keyword screening; multiple categories per post possible",
        "limitations": [
            "Flags are not hate-speech labels; context and target of speech require manual review",
            "The lexicon has not been validated; both false positives and false negatives are expected",
            "Political domain is based on sampling query, not verified topic classification",
            "Data are sampled posts, not the full X population",
        ],
    }
    (out / "political_language_summary_week3.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports"))
    args = parser.parse_args()
    print(json.dumps(analyze(args.source, args.out), ensure_ascii=False, indent=2))
