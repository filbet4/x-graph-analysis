"""Create a reproducible annotation sample from collected conversations."""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_multidomain_conversations.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "multidomain_annotation_sample.csv"
)

SAMPLE_SIZE = 100
RANDOM_SEED = 42


def get_text(record: dict[str, Any]) -> str:
    """Extract tweet text from common Scweet fields."""
    for key in ("text", "full_text", "tweet_text"):
        value = record.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    value = legacy.get("full_text")

    if isinstance(value, str) and value.strip():
        return value.strip()

    return ""


def clean_text(text: str) -> str:
    """Normalize whitespace for CSV output."""
    return " ".join(text.split())


def get_contexts(item: dict[str, Any]) -> list[dict[str, Any]]:
    return item.get("collection_contexts", [])


def get_root_id(item: dict[str, Any]) -> str | None:
    contexts = get_contexts(item)

    if not contexts:
        return None

    root_id = contexts[0].get("root_id")

    return str(root_id) if root_id else None


def get_sampling_domain(item: dict[str, Any]) -> str:
    contexts = get_contexts(item)

    if not contexts:
        return ""

    return str(contexts[0].get("sampling_domain", ""))


def main() -> None:
    random.seed(RANDOM_SEED)

    data = json.loads(
        INPUT_PATH.read_text(encoding="utf-8")
    )

    records = data["records"]

    by_id = {
        str(item["tweet_id"]): item
        for item in records
    }

    # Group posts by conversation root.
    conversations: dict[str, list[dict[str, Any]]] = {}

    for item in records:
        root_id = get_root_id(item)

        if root_id is None:
            continue

        conversations.setdefault(root_id, []).append(item)

    selected: dict[str, dict[str, Any]] = {}

    # Always include every selected root.
    for root_info in data["selected_roots"]:
        root_id = str(root_info["tweet_id"])

        if root_id in by_id:
            selected[root_id] = by_id[root_id]

    remaining_slots = SAMPLE_SIZE - len(selected)

    if remaining_slots < 0:
        raise RuntimeError(
            "SAMPLE_SIZE is smaller than the number of roots."
        )

    # Prepare non-root candidates for each conversation.
    candidates_by_root: dict[str, list[dict[str, Any]]] = {}

    for root_id, items in conversations.items():
        candidates = [
            item
            for item in items
            if str(item["tweet_id"]) != root_id
        ]

        random.shuffle(candidates)
        candidates_by_root[root_id] = candidates

    root_ids = sorted(candidates_by_root)

    # Round-robin sampling keeps conversations reasonably balanced.
    while remaining_slots > 0:
        added_in_round = False

        for root_id in root_ids:
            if remaining_slots == 0:
                break

            candidates = candidates_by_root[root_id]

            while candidates:
                item = candidates.pop()
                tweet_id = str(item["tweet_id"])

                if tweet_id not in selected:
                    selected[tweet_id] = item
                    remaining_slots -= 1
                    added_in_round = True
                    break

        if not added_in_round:
            break

    if len(selected) < SAMPLE_SIZE:
        raise RuntimeError(
            f"Could only select {len(selected)} unique posts "
            f"out of requested {SAMPLE_SIZE}."
        )

    rows: list[dict[str, Any]] = []

    for tweet_id, item in selected.items():
        record = item["record"]

        root_id = get_root_id(item)
        root_item = by_id.get(root_id) if root_id else None

        text = clean_text(get_text(record))

        root_text = ""

        if root_item is not None:
            root_text = clean_text(
                get_text(root_item["record"])
            )

        is_root = tweet_id == root_id

        rows.append(
            {
                "tweet_id": tweet_id,
                "root_id": root_id or "",
                "sampling_domain": get_sampling_domain(item),
                "is_root": int(is_root),
                "text": text,
                "root_context": root_text,
                # Manual annotation columns:
                "language": "",
                "politics": "",
                "sport": "",
                "pop_culture": "",
                "other": "",
                "notes": "",
            }
        )

    rows.sort(
        key=lambda row: (
            row["sampling_domain"],
            row["root_id"],
            -row["is_root"],
            row["tweet_id"],
        )
    )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = [
        "tweet_id",
        "root_id",
        "sampling_domain",
        "is_root",
        "text",
        "root_context",
        "language",
        "politics",
        "sport",
        "pop_culture",
        "other",
        "notes",
    ]

    with OUTPUT_PATH.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(rows)

    print("=== ANNOTATION SAMPLE CREATED ===")
    print(f"Available posts: {len(records)}")
    print(f"Selected posts: {len(rows)}")
    print(f"Random seed: {RANDOM_SEED}")
    print(f"Output: {OUTPUT_PATH}")

    print()
    print("Posts by sampling domain:")

    domain_counts: dict[str, int] = {}

    for row in rows:
        domain = row["sampling_domain"]
        domain_counts[domain] = (
            domain_counts.get(domain, 0) + 1
        )

    for domain, count in sorted(domain_counts.items()):
        print(f"  {domain}: {count}")

    print()
    print(
        "Open the CSV in Excel and fill only: "
        "language, politics, sport, pop_culture, other, notes."
    )


if __name__ == "__main__":
    main()