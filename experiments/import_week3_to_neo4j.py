"""Safely prepare or import the 21-27 October 2026 dataset into Neo4j."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase

from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper
from x_graph_analysis.config import Settings
from x_graph_analysis.domain.models import Post

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    PROJECT_ROOT / "data" / "scweet_large_sample_2026-10-21_2026-10-27.json"
)
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "week3_neo4j_import_report.json"
DATABASES = ("xgraph", "xgraph-expanded")
RELATIONSHIP_TYPES = ("REPLY", "QUOTE", "REPOST")
REQUIRED_UNIQUE_CONSTRAINTS = {
    ("Post", "post_id"),
    ("User", "user_id"),
    ("Hashtag", "normalized_text"),
}


@dataclass(frozen=True, slots=True)
class ImportPlan:
    """Mapped week-three posts and direct interaction relationships."""

    posts: tuple[Post, ...]
    relationships: tuple[dict[str, str], ...]
    mapping_errors: tuple[dict[str, str], ...]


@dataclass(frozen=True, slots=True)
class DatabaseSnapshot:
    """Read-only counts used before and after an import."""

    status: str
    node_counts: dict[str, int]
    relationship_counts: dict[str, int]
    existing_posts: int = 0
    existing_users: int = 0
    existing_hashtags: int = 0
    existing_relationships_touching_week3: dict[str, int] | None = None
    relationship_target_status: dict[str, dict[str, int]] | None = None
    constraints: tuple[dict[str, Any], ...] = ()
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "node_counts": self.node_counts,
            "relationship_counts": self.relationship_counts,
            "existing_week3_posts": self.existing_posts,
            "existing_week3_users": self.existing_users,
            "existing_week3_hashtags": self.existing_hashtags,
            "existing_week3_relationships": (
                self.existing_relationships_touching_week3 or {}
            ),
            "relationship_target_status": self.relationship_target_status or {},
            "constraints": list(self.constraints),
            "error": self.error,
        }


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON object."""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("source JSON must contain an object")
    return value


def post_row(post: Post) -> dict[str, Any]:
    """Build parameters without overwriting existing Neo4j properties."""
    metrics = post.metrics
    return {
        "post_id": post.post_id,
        "author": {
            "user_id": post.author.user_id,
            "username": post.author.username,
            "display_name": post.author.display_name,
            "verified": post.author.verified,
        },
        "text": post.text,
        "published_at": post.published_at,
        "like_count": metrics.like_count if metrics else 0,
        "repost_count": metrics.repost_count if metrics else 0,
        "reply_count": metrics.reply_count if metrics else 0,
        "quote_count": metrics.quote_count if metrics else 0,
        "view_count": metrics.view_count if metrics else None,
        "hashtags": [
            {
                "text": hashtag.text,
                "normalized_text": hashtag.normalized_text,
            }
            for hashtag in post.hashtags
        ],
    }


def load_import_plan(path: Path = DEFAULT_SOURCE) -> ImportPlan:
    """Map week-three records and extract all direct interaction references."""
    data = load_json(path)
    records = data.get("records")
    if not isinstance(records, list):
        raise ValueError("source JSON field 'records' must be a list")

    mapper = ScweetPostMapper()
    posts: dict[str, Post] = {}
    errors: list[dict[str, str]] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("tweet_id", ""))
        try:
            post = mapper.map_seed(item)
        except (KeyError, TypeError, ValueError) as error:
            errors.append({"post_id": post_id, "error": str(error)})
            continue
        previous = posts.get(post.post_id)
        if previous is not None and previous != post:
            errors.append(
                {
                    "post_id": post.post_id,
                    "error": "duplicate post_id has conflicting mapped records",
                }
            )
            continue
        posts[post.post_id] = post

    relationships: set[tuple[str, str, str]] = set()
    for post in posts.values():
        for relationship_type, target_id in (
            ("REPLY", post.reply_to_post_id),
            ("QUOTE", post.quoted_post_id),
            ("REPOST", post.reposted_post_id),
        ):
            if target_id and target_id != post.post_id:
                relationships.add((post.post_id, target_id, relationship_type))

    return ImportPlan(
        posts=tuple(posts[post_id] for post_id in sorted(posts)),
        relationships=tuple(
            {
                "source_post_id": source,
                "target_post_id": target,
                "type": relationship_type,
            }
            for source, target, relationship_type in sorted(relationships)
        ),
        mapping_errors=tuple(errors),
    )


def plan_summary(plan: ImportPlan) -> dict[str, Any]:
    """Summarize local data without connecting to Neo4j."""
    authors = {post.author.user_id for post in plan.posts}
    hashtags = {
        hashtag.normalized_text for post in plan.posts for hashtag in post.hashtags
    }
    relationship_counts = Counter(row["type"] for row in plan.relationships)
    return {
        "source_posts": len(plan.posts),
        "source_authors": len(authors),
        "source_hashtags": len(hashtags),
        "source_relationships": dict(relationship_counts),
        "mapping_errors": len(plan.mapping_errors),
        "relationship_targets_may_be_existing_posts": sum(
            row["target_post_id"] not in {post.post_id for post in plan.posts}
            for row in plan.relationships
        ),
    }


def database_snapshot(
    driver: Any,
    database: str,
    plan: ImportPlan,
) -> DatabaseSnapshot:
    """Read node and relationship counts from one database."""
    post_ids = [post.post_id for post in plan.posts]
    user_ids = sorted({post.author.user_id for post in plan.posts})
    hashtag_ids = sorted(
        {hashtag.normalized_text for post in plan.posts for hashtag in post.hashtags}
    )
    try:
        with driver.session(database=database) as session:
            node_rows = session.run(
                """
                MATCH (n)
                UNWIND labels(n) AS label
                RETURN label, count(*) AS count
                ORDER BY label
                """
            ).data()
            relationship_rows = session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(*) AS count
                ORDER BY type
                """
            ).data()
            existing_posts = session.run(
                """
                UNWIND $ids AS id
                MATCH (n:Post {post_id: id})
                RETURN count(n) AS count
                """,
                ids=post_ids,
            ).single()["count"]
            existing_users = session.run(
                """
                UNWIND $ids AS id
                MATCH (n:User {user_id: id})
                RETURN count(n) AS count
                """,
                ids=user_ids,
            ).single()["count"]
            existing_hashtags = session.run(
                """
                UNWIND $ids AS id
                MATCH (n:Hashtag {normalized_text: id})
                RETURN count(n) AS count
                """,
                ids=hashtag_ids,
            ).single()["count"]
            touching_rows = session.run(
                """
                UNWIND $ids AS id
                MATCH (a:Post)-[r]->(b:Post)
                WHERE a.post_id = id OR b.post_id = id
                RETURN type(r) AS type, count(DISTINCT r) AS count
                ORDER BY type
                """,
                ids=post_ids,
            ).data()
            target_rows = session.run(
                """
                UNWIND $relationships AS row
                OPTIONAL MATCH (target:Post {post_id: row.target_post_id})
                RETURN row.type AS type,
                       count(*) AS requested,
                       count(target) AS target_exists
                ORDER BY type
                """,
                relationships=list(plan.relationships),
            ).data()
            constraint_rows = session.run(
                """
                SHOW CONSTRAINTS
                YIELD name, type, entityType, labelsOrTypes, properties
                RETURN name, type, entityType, labelsOrTypes, properties
                ORDER BY name
                """
            ).data()
        return DatabaseSnapshot(
            status="ok",
            node_counts={row["label"]: row["count"] for row in node_rows},
            relationship_counts={
                row["type"]: row["count"] for row in relationship_rows
            },
            existing_posts=existing_posts,
            existing_users=existing_users,
            existing_hashtags=existing_hashtags,
            existing_relationships_touching_week3={
                row["type"]: row["count"] for row in touching_rows
            },
            relationship_target_status={
                row["type"]: {
                    "requested": row["requested"],
                    "target_exists": row["target_exists"],
                }
                for row in target_rows
            },
            constraints=tuple(constraint_rows),
        )
    except Exception as error:
        return DatabaseSnapshot(
            status="error",
            node_counts={},
            relationship_counts={},
            error=f"{type(error).__name__}: {error}",
        )


def missing_constraints(snapshot: DatabaseSnapshot) -> set[tuple[str, str]]:
    """Return required uniqueness constraints absent from a snapshot."""
    present: set[tuple[str, str]] = set()
    for constraint in snapshot.constraints:
        labels = constraint.get("labelsOrTypes") or []
        properties = constraint.get("properties") or []
        for label in labels:
            for property_name in properties:
                present.add((str(label), str(property_name)))
    return REQUIRED_UNIQUE_CONSTRAINTS - present


def count_deltas(
    before: dict[str, Any],
    after: dict[str, Any],
) -> dict[str, dict[str, int]]:
    """Calculate actual node and relationship count changes."""
    before_nodes = before.get("node_counts", {})
    after_nodes = after.get("node_counts", {})
    before_relationships = before.get("relationship_counts", {})
    after_relationships = after.get("relationship_counts", {})
    labels = set(before_nodes) | set(after_nodes)
    relationship_types = set(before_relationships) | set(after_relationships)
    return {
        "nodes": {
            label: int(after_nodes.get(label, 0)) - int(before_nodes.get(label, 0))
            for label in sorted(labels)
        },
        "relationships": {
            relationship_type: int(after_relationships.get(relationship_type, 0))
            - int(before_relationships.get(relationship_type, 0))
            for relationship_type in sorted(relationship_types)
        },
    }


def import_plan(driver: Any, database: str, plan: ImportPlan) -> None:
    """Merge only week-three entities and direct interaction relationships."""
    rows = [post_row(post) for post in plan.posts]
    with driver.session(database=database) as session:
        session.run(
            """
            UNWIND $posts AS row
            MERGE (u:User {user_id: row.author.user_id})
            ON CREATE SET u.username = row.author.username,
                          u.display_name = row.author.display_name,
                          u.verified = row.author.verified
            MERGE (p:Post {post_id: row.post_id})
            ON CREATE SET p.text = row.text,
                          p.published_at = row.published_at,
                          p.like_count = row.like_count,
                          p.repost_count = row.repost_count,
                          p.reply_count = row.reply_count,
                          p.quote_count = row.quote_count,
                          p.view_count = row.view_count
            MERGE (u)-[:AUTHORED]->(p)
            WITH p, row
            UNWIND row.hashtags AS h
            MERGE (tag:Hashtag {normalized_text: h.normalized_text})
            ON CREATE SET tag.text = h.text
            MERGE (p)-[:HAS_HASHTAG]->(tag)
            """,
            posts=rows,
        ).consume()
        for relationship_type in RELATIONSHIP_TYPES:
            relationships = [
                row for row in plan.relationships if row["type"] == relationship_type
            ]
            if not relationships:
                continue
            session.run(
                f"""
                UNWIND $relationships AS row
                MATCH (source:Post {{post_id: row.source_post_id}})
                MATCH (target:Post {{post_id: row.target_post_id}})
                MERGE (source)-[:{relationship_type}]->(target)
                """,
                relationships=relationships,
            ).consume()


def run(
    plan: ImportPlan,
    *,
    database: str,
    execute: bool,
    report_path: Path,
) -> dict[str, Any]:
    """Run dry-run or a guarded import for one explicitly selected database."""
    if database not in DATABASES:
        raise ValueError(f"database must be one of {DATABASES}")
    result: dict[str, Any] = {
        "database": database,
        "mode": "execute" if execute else "dry_run",
        "source": plan_summary(plan),
        "before": {"status": "not_queried"},
        "after": {"status": "not_queried"},
    }
    if not execute:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    settings = Settings.from_environment()
    if not settings.neo4j_password:
        raise RuntimeError("X_GRAPH_ANALYSIS_NEO4J_PASSWORD is not set")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    try:
        before_snapshot = database_snapshot(driver, database, plan)
        result["before"] = before_snapshot.as_dict()
        missing = missing_constraints(before_snapshot)
        if before_snapshot.status != "ok" or missing:
            result["status"] = "aborted_preflight"
            result["preflight_errors"] = {
                "missing_constraints": sorted(missing),
                "snapshot_error": before_snapshot.error,
            }
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            raise RuntimeError(
                "Preflight failed before write: "
                f"missing_constraints={sorted(missing)}, "
                f"snapshot_error={before_snapshot.error}"
            )
        import_plan(driver, database, plan)
        after_snapshot = database_snapshot(driver, database, plan)
        result["after"] = after_snapshot.as_dict()
        result["delta"] = count_deltas(
            result["before"],
            result["after"],
        )
    finally:
        driver.close()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    """Print a dry-run by default; require --execute for writes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", choices=DATABASES, required=True)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = load_import_plan(args.source)
    result = run(
        plan,
        database=args.database,
        execute=args.execute,
        report_path=args.report,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
