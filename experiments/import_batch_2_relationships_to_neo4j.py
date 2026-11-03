"""Import Batch 1 post relationships into Neo4j."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from x_graph_analysis.adapters.persistence.neo4j import Neo4jGraphRepository
from x_graph_analysis.config import Settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEED_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_large_sample_2026-10-14_2026-10-20.json"
)

TARGET_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_one_hop_targets_2026-10-14_2026-10-20.json"
)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def extract_post_id(item: dict[str, Any]) -> str | None:
    """Extract a post ID from a seed wrapper or raw one-hop target."""
    post_id = item.get("tweet_id")

    if post_id is not None:
        return str(post_id)

    record = item.get("record")

    if isinstance(record, dict):
        post_id = record.get("tweet_id")

        if post_id is not None:
            return str(post_id)

    raw = item

    if raw.get("__typename") == "TweetWithVisibilityResults":
        tweet = raw.get("tweet")

        if isinstance(tweet, dict):
            raw = tweet

    post_id = raw.get("rest_id")

    if post_id is not None:
        return str(post_id)

    legacy = raw.get("legacy")

    if isinstance(legacy, dict):
        post_id = legacy.get("id_str")

        if post_id is not None:
            return str(post_id)

    return None


def extract_target_id(
    item: dict[str, Any],
    relationship_type: str,
) -> str | None:
    """Extract a direct relationship target ID."""
    record = item.get("record", item)

    if relationship_type == "REPLY":
        target_id = record.get("in_reply_to_tweet_id")
        return str(target_id) if target_id is not None else None

    if relationship_type == "QUOTE":
        quoted_tweet = record.get("quoted_tweet")

        if not isinstance(quoted_tweet, dict):
            return None

        target_id = quoted_tweet.get("tweet_id")
        return str(target_id) if target_id is not None else None

    return None


def build_relationships() -> list[dict[str, str]]:
    """Build direct relationships originating only from Search seeds."""
    seed_data = load_json(SEED_PATH)
    target_data = load_json(TARGET_PATH)

    seeds = seed_data["records"]
    targets = target_data["retrieved_records"]

    available_ids = {
        post_id
        for record in seeds + targets
        if (post_id := extract_post_id(record)) is not None
    }

    relationships: list[dict[str, str]] = []



    for record in seeds:
        source_id = extract_post_id(record)

        if source_id is None:
            continue

        for relationship_type in ("REPLY", "QUOTE"):
            target_id = extract_target_id(record, relationship_type)

            if target_id is None or target_id not in available_ids:
                continue

            relationships.append(
                {
                    "source_post_id": source_id,
                    "target_post_id": target_id,
                    "type": relationship_type,
                }
            )

    return relationships


def main() -> None:
    """Validate and import Batch 2 relationships."""
    relationships = build_relationships()

    counts = Counter(
        relationship["type"]
        for relationship in relationships
    )

    print(f"REPLY: {counts['REPLY']}")
    print(f"QUOTE: {counts['QUOTE']}")
    print(f"TOTAL: {len(relationships)}")

    # Safety check before touching Neo4j.
    if counts["REPLY"] != 1479 or counts["QUOTE"] != 240:
        raise RuntimeError(
            "Relationship counts do not match the validated "
            "Batch 2 extraction."
        )

    settings = Settings.from_environment()

    if settings.neo4j_password is None:
        raise RuntimeError(
            "X_GRAPH_ANALYSIS_NEO4J_PASSWORD is not set."
        )

    repository = Neo4jGraphRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )

    try:
        repository.verify_connectivity()
        repository.save_post_relationships(relationships)
    finally:
        repository.close()

    print("Relationships imported successfully.")

if __name__ == "__main__":
    main()