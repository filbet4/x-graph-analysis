"""Import the first collected dataset into Neo4j."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from x_graph_analysis.adapters.persistence.neo4j import Neo4jGraphRepository
from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper
from x_graph_analysis.config import Settings
from x_graph_analysis.domain.models import Post

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SEED_PATH = PROJECT_ROOT / "data" / "scweet_large_sample.json"
TARGET_PATH = PROJECT_ROOT / "data" / "scweet_one_hop_targets.json"


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_posts() -> tuple[list[Post], list[str], list[str]]:
    """Load and map Search seeds and one-hop targets."""
    mapper = ScweetPostMapper()

    seed_data = load_json(SEED_PATH)
    target_data = load_json(TARGET_PATH)

    seed_posts = [
        mapper.map_seed(item)
        for item in seed_data["records"]
    ]

    target_posts = [
        mapper.map_target(record)
        for record in target_data["retrieved_records"]
    ]

    posts_by_id = {
        post.post_id: post
        for post in seed_posts + target_posts
    }

    print(f"Search seeds:    {len(seed_posts)}")
    print(f"One-hop targets: {len(target_posts)}")
    print(f"Unique posts:    {len(posts_by_id)}")

    seed_post_ids = [post.post_id for post in seed_posts]
    target_post_ids = [post.post_id for post in target_posts]

    return (
        list(posts_by_id.values()),
        seed_post_ids,
        target_post_ids,
    )


def main() -> None:
    """Import the first dataset into Neo4j."""
    settings = Settings.from_environment()

    if settings.neo4j_password is None:
        raise RuntimeError(
            "X_GRAPH_ANALYSIS_NEO4J_PASSWORD is not set."
        )

    posts, seed_post_ids, target_post_ids = load_posts()

    repository = Neo4jGraphRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )

    try:
        repository.verify_connectivity()
        repository.create_constraints()

        print()
        print("Importing posts...")
        repository.save_posts(posts)
        repository.set_post_origins(
        seed_post_ids=seed_post_ids,
        target_post_ids=target_post_ids,
    )
        print("Import finished.")
    finally:
        repository.close()


if __name__ == "__main__":
    main()