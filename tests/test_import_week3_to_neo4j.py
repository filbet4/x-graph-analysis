"""Tests for the read-only/deduplicating week-three Neo4j importer."""

import json
from pathlib import Path

from experiments.import_week3_to_neo4j import (
    DEFAULT_SOURCE,
    DatabaseSnapshot,
    ImportPlan,
    count_deltas,
    import_plan,
    load_import_plan,
    missing_constraints,
    plan_summary,
    run,
)


class FakeResult:
    def consume(self) -> None:
        return None


class FakeSession:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, object]]] = []

    def __enter__(self) -> "FakeSession":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def run(self, query: str, **parameters: object) -> FakeResult:
        self.queries.append((query, parameters))
        return FakeResult()


class FakeDriver:
    def __init__(self) -> None:
        self.session_instance = FakeSession()

    def session(self, *, database: str) -> FakeSession:
        del database
        return self.session_instance


def test_week3_plan_matches_local_source() -> None:
    plan = load_import_plan(DEFAULT_SOURCE)
    summary = plan_summary(plan)

    assert summary["source_posts"] == 2808
    assert summary["mapping_errors"] == 0
    assert summary["source_relationships"]["REPLY"] == 1314
    assert summary["source_relationships"]["QUOTE"] == 260
    assert set(summary["source_relationships"]) <= {"REPLY", "QUOTE", "REPOST"}


def test_import_queries_are_non_destructive_and_preserve_expanded_relations() -> None:
    plan = ImportPlan(
        posts=(),
        relationships=(
            {
                "source_post_id": "1",
                "target_post_id": "2",
                "type": "REPLY",
            },
        ),
        mapping_errors=(),
    )
    driver = FakeDriver()

    import_plan(driver, "xgraph-expanded", plan)
    import_plan(driver, "xgraph-expanded", plan)

    queries = [query for query, _parameters in driver.session_instance.queries]
    assert len(queries) == 4
    assert all("MERGE" in query for query in queries)
    assert all("DELETE" not in query for query in queries)
    assert all("SIMILAR" not in query for query in queries)
    assert "ON CREATE SET" in queries[0]
    assert queries[1] == queries[3]


def test_dry_run_writes_report_without_database_access(tmp_path: Path) -> None:
    plan = load_import_plan(DEFAULT_SOURCE)
    report = tmp_path / "dry-run.json"

    result = run(
        plan,
        database="xgraph",
        execute=False,
        report_path=report,
    )

    saved = json.loads(report.read_text(encoding="utf-8"))
    assert result == saved
    assert result["mode"] == "dry_run"
    assert result["before"]["status"] == "not_queried"
    assert result["after"]["status"] == "not_queried"


def test_required_constraints_are_checked() -> None:
    snapshot = DatabaseSnapshot(
        status="ok",
        node_counts={},
        relationship_counts={},
        constraints=(
            {"labelsOrTypes": ["Post"], "properties": ["post_id"]},
            {"labelsOrTypes": ["User"], "properties": ["user_id"]},
            {"labelsOrTypes": ["Hashtag"], "properties": ["normalized_text"]},
        ),
    )

    assert missing_constraints(snapshot) == set()


def test_count_deltas_reports_new_nodes_and_relationships() -> None:
    before = {
        "node_counts": {"Post": 10, "User": 5},
        "relationship_counts": {"AUTHORED": 10, "REPLY": 3},
    }
    after = {
        "node_counts": {"Post": 12, "User": 6, "Hashtag": 1},
        "relationship_counts": {
            "AUTHORED": 12,
            "REPLY": 4,
            "QUOTE": 2,
        },
    }

    assert count_deltas(before, after) == {
        "nodes": {"Hashtag": 1, "Post": 2, "User": 1},
        "relationships": {
            "AUTHORED": 2,
            "QUOTE": 2,
            "REPLY": 1,
        },
    }
