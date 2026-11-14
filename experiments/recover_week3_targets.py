"""Recover week-three REPLY/QUOTE targets from local records only."""

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

try:
    from .import_week3_to_neo4j import (
        DatabaseSnapshot,
        count_deltas,
        missing_constraints,
    )
except ImportError:
    from import_week3_to_neo4j import (
        DatabaseSnapshot,
        count_deltas,
        missing_constraints,
    )

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEEK3 = PROJECT_ROOT / "data" / "scweet_large_sample_2026-10-21_2026-10-27.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "week3_target_recovery.json"
DATABASE = "xgraph"
RELATIONSHIP_TYPES = ("REPLY", "QUOTE")
REQUIRED_CONSTRAINTS = {
    ("Post", "post_id"),
    ("User", "user_id"),
    ("Hashtag", "normalized_text"),
}
SOURCE_PRIORITY = {
    "one_hop": 4,
    "merged": 3,
    "conversation": 2,
    "week3": 1,
    "other": 0,
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One locally available mapped target candidate."""

    post: Post
    source: str
    source_path: str
    quality_score: int


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    """Missing week-three target relationships and selected local posts."""

    week3_posts: tuple[Post, ...]
    relationships: tuple[dict[str, str], ...]
    candidates: tuple[Candidate, ...]
    unavailable_target_ids: tuple[str, ...]
    rejected_candidates: tuple[dict[str, str], ...]


def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def classify_source(path: Path) -> str:
    name = path.name
    if "one_hop_targets" in name:
        return "one_hop"
    if "merged" in name:
        return "merged"
    if "conversation" in name:
        return "conversation"
    if "large_sample_2026-10-21_2026-10-27" in name:
        return "week3"
    return "other"


def iter_records(path: Path) -> list[dict[str, Any]]:
    """Return records from supported local JSON shapes."""
    value = load_json(path)
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []
    rows: list[dict[str, Any]] = []
    for key in ("records", "retrieved_records"):
        records = value.get(key)
        if isinstance(records, list):
            rows.extend(row for row in records if isinstance(row, dict))
    return rows


def map_record(
    row: dict[str, Any],
    mapper: ScweetPostMapper,
) -> Post:
    """Map a Search wrapper or raw target record using the existing mapper."""
    nested = row.get("record")
    if isinstance(nested, dict):
        if isinstance(nested.get("raw"), dict):
            return mapper.map_seed(row)
        return mapper.map_target(nested)
    return mapper.map_target(row)


def quality_score(post: Post, source: str) -> int:
    """Score only facts required for a safe Post/User import."""
    score = SOURCE_PRIORITY[source] * 10
    if post.post_id:
        score += 1
    if post.author.user_id:
        score += 1
    if post.author.username:
        score += 1
    if post.text.strip():
        score += 2
    if post.published_at.tzinfo is not None:
        score += 1
    return score


def build_recovery_plan(
    week3_path: Path = DEFAULT_WEEK3,
    data_dir: Path = PROJECT_ROOT / "data",
) -> RecoveryPlan:
    """Build a deduplicated recovery plan from local JSON files."""
    mapper = ScweetPostMapper()
    week3_rows = iter_records(week3_path)
    week3_posts: dict[str, Post] = {}
    for row in week3_rows:
        post = map_record(row, mapper)
        week3_posts[post.post_id] = post

    relationships: set[tuple[str, str, str]] = set()
    for post in week3_posts.values():
        for relationship_type, target_id in (
            ("REPLY", post.reply_to_post_id),
            ("QUOTE", post.quoted_post_id),
        ):
            if target_id and target_id != post.post_id:
                relationships.add((post.post_id, target_id, relationship_type))
    target_ids = {target for _, target, _ in relationships}

    candidates_by_id: dict[str, Candidate] = {}
    rejected: list[dict[str, str]] = []
    for path in sorted(data_dir.glob("*.json")):
        source = classify_source(path)
        for row in iter_records(path):
            try:
                post = map_record(row, mapper)
            except (KeyError, TypeError, ValueError) as error:
                rejected.append(
                    {
                        "source_path": str(path.relative_to(PROJECT_ROOT)),
                        "error": str(error),
                    }
                )
                continue
            if post.post_id not in target_ids:
                continue
            score = quality_score(post, source)
            if (
                not post.author.user_id
                or not post.author.username
                or not post.text.strip()
            ):
                rejected.append(
                    {
                        "post_id": post.post_id,
                        "source_path": str(path.relative_to(PROJECT_ROOT)),
                        "error": "missing required Post/User/text field",
                    }
                )
                continue
            candidate = Candidate(
                post=post,
                source=source,
                source_path=str(path.relative_to(PROJECT_ROOT)),
                quality_score=score,
            )
            previous = candidates_by_id.get(post.post_id)
            if previous is None or candidate.quality_score > previous.quality_score:
                candidates_by_id[post.post_id] = candidate

    unavailable = tuple(sorted(target_ids - set(candidates_by_id)))
    return RecoveryPlan(
        week3_posts=tuple(week3_posts[post_id] for post_id in sorted(week3_posts)),
        relationships=tuple(
            {
                "source_post_id": source,
                "target_post_id": target,
                "type": relationship_type,
            }
            for source, target, relationship_type in sorted(relationships)
        ),
        candidates=tuple(
            candidates_by_id[post_id] for post_id in sorted(candidates_by_id)
        ),
        unavailable_target_ids=unavailable,
        rejected_candidates=tuple(rejected),
    )


def plan_summary(plan: RecoveryPlan) -> dict[str, Any]:
    """Summarize local recovery candidates and relations."""
    relation_counts = Counter(row["type"] for row in plan.relationships)
    candidate_ids = {candidate.post.post_id for candidate in plan.candidates}
    recoverable = Counter(
        row["type"]
        for row in plan.relationships
        if row["target_post_id"] in candidate_ids
    )
    return {
        "week3_posts": len(plan.week3_posts),
        "requested_relationships": dict(relation_counts),
        "unique_targets": len({row["target_post_id"] for row in plan.relationships}),
        "local_full_targets": len(plan.candidates),
        "unavailable_targets": len(plan.unavailable_target_ids),
        "rejected_candidates": len(plan.rejected_candidates),
        "recoverable_relationships": dict(recoverable),
        "unavailable_target_ids": list(plan.unavailable_target_ids),
    }


def post_row(post: Post) -> dict[str, Any]:
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
            {"text": tag.text, "normalized_text": tag.normalized_text}
            for tag in post.hashtags
        ],
    }


def snapshot(driver: Any, plan: RecoveryPlan) -> DatabaseSnapshot:
    """Read xgraph counts and target/relationship existence."""
    candidate_ids = [candidate.post.post_id for candidate in plan.candidates]
    user_ids = sorted({candidate.post.author.user_id for candidate in plan.candidates})
    hashtag_ids = sorted(
        {
            tag.normalized_text
            for candidate in plan.candidates
            for tag in candidate.post.hashtags
        }
    )
    try:
        with driver.session(database=DATABASE) as session:
            nodes = session.run(
                """
                MATCH (n)
                UNWIND labels(n) AS label
                RETURN label, count(*) AS count
                ORDER BY label
                """
            ).data()
            relationships = session.run(
                """
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(*) AS count
                ORDER BY type
                """
            ).data()
            existing_posts = session.run(
                """
                UNWIND $ids AS id
                MATCH (p:Post {post_id: id})
                RETURN count(p) AS count
                """,
                ids=candidate_ids,
            ).single()["count"]
            existing_users = session.run(
                """
                UNWIND $ids AS id
                MATCH (u:User {user_id: id})
                RETURN count(u) AS count
                """,
                ids=user_ids,
            ).single()["count"]
            existing_hashtags = session.run(
                """
                UNWIND $ids AS id
                MATCH (h:Hashtag {normalized_text: id})
                RETURN count(h) AS count
                """,
                ids=hashtag_ids,
            ).single()["count"]
            existing_relationships = session.run(
                """
                UNWIND $relationships AS row
                MATCH (source:Post {post_id: row.source_post_id})
                MATCH (target:Post {post_id: row.target_post_id})
                OPTIONAL MATCH (source)-[r]->(target)
                WHERE type(r) = row.type
                RETURN row.type AS type, count(DISTINCT r) AS count
                ORDER BY type
                """,
                relationships=list(plan.relationships),
            ).data()
            constraints = session.run(
                """
                SHOW CONSTRAINTS
                YIELD name, type, entityType, labelsOrTypes, properties
                RETURN name, type, entityType, labelsOrTypes, properties
                ORDER BY name
                """
            ).data()
        return DatabaseSnapshot(
            status="ok",
            node_counts={row["label"]: row["count"] for row in nodes},
            relationship_counts={row["type"]: row["count"] for row in relationships},
            existing_posts=existing_posts,
            existing_users=existing_users,
            existing_hashtags=existing_hashtags,
            existing_relationships_touching_week3={
                row["type"]: row["count"] for row in existing_relationships
            },
            constraints=tuple(constraints),
        )
    except Exception as error:
        return DatabaseSnapshot(
            status="error",
            node_counts={},
            relationship_counts={},
            error=f"{type(error).__name__}: {error}",
        )


def import_recovery(driver: Any, plan: RecoveryPlan) -> None:
    """Merge target entities and only week-three REPLY/QUOTE edges."""
    rows = [post_row(candidate.post) for candidate in plan.candidates]
    with driver.session(database=DATABASE) as session:
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
        available_ids = {candidate.post.post_id for candidate in plan.candidates}
        for relationship_type in RELATIONSHIP_TYPES:
            relationships = [
                row
                for row in plan.relationships
                if row["type"] == relationship_type
                and row["target_post_id"] in available_ids
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
    plan: RecoveryPlan,
    *,
    execute: bool,
    report_path: Path,
) -> dict[str, Any]:
    """Run local dry-run or guarded xgraph-only recovery."""
    result: dict[str, Any] = {
        "database": DATABASE,
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
        before = snapshot(driver, plan)
        result["before"] = before.as_dict()
        missing = missing_constraints(before)
        if before.status != "ok" or missing:
            result["status"] = "aborted_preflight"
            result["preflight_errors"] = {
                "missing_constraints": sorted(missing),
                "snapshot_error": before.error,
            }
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            raise RuntimeError(f"Preflight failed: {result['preflight_errors']}")
        import_recovery(driver, plan)
        after = snapshot(driver, plan)
        result["after"] = after.as_dict()
        result["delta"] = count_deltas(result["before"], result["after"])
    finally:
        driver.close()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week3", type=Path, default=DEFAULT_WEEK3)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    plan = build_recovery_plan(args.week3, args.data_dir)
    result = run(plan, execute=args.execute, report_path=args.report)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
