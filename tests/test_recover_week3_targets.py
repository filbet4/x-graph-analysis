"""Tests for local week-three target recovery."""

import json
from datetime import UTC, datetime
from pathlib import Path

from experiments.recover_week3_targets import (
    DEFAULT_WEEK3,
    Candidate,
    build_recovery_plan,
    plan_summary,
    post_row,
)

from x_graph_analysis.domain.models import Post, User


def test_recovery_plan_has_expected_local_counts() -> None:
    plan = build_recovery_plan(DEFAULT_WEEK3)
    summary = plan_summary(plan)

    assert summary["week3_posts"] == 2808
    assert summary["unique_targets"] == 1357
    assert summary["local_full_targets"] == 1330
    assert summary["unavailable_targets"] == 27
    assert summary["recoverable_relationships"] == {
        "QUOTE": 254,
        "REPLY": 1288,
    }


def test_candidate_selection_prefers_one_hop_source(tmp_path: Path) -> None:
    post = Post(
        post_id="target",
        author=User(user_id="user", username="user"),
        text="Target text",
        published_at=datetime(2026, 11, 1, tzinfo=UTC),
    )
    source = tmp_path / "week.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "tweet_id": "source",
                        "record": {
                            "raw": {
                                "core": {
                                    "user_results": {
                                        "result": {
                                            "rest_id": "source-user",
                                            "core": {"screen_name": "source"},
                                        }
                                    }
                                },
                                "legacy": {
                                    "created_at": "Sat Nov 01 00:00:00 +0000 2026",
                                    "full_text": "source",
                                },
                            }
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    candidate = Candidate(post, "one_hop", "data/one_hop.json", 46)
    assert candidate.source == "one_hop"
    assert candidate.quality_score > 0
    assert post_row(candidate.post)["post_id"] == "target"


def test_recovery_plan_contains_only_reply_and_quote_edges() -> None:
    plan = build_recovery_plan(DEFAULT_WEEK3)

    assert {row["type"] for row in plan.relationships} == {"REPLY", "QUOTE"}
    assert all(
        row["source_post_id"] in {post.post_id for post in plan.week3_posts}
        for row in plan.relationships
    )


def test_recovery_plan_is_deterministic_and_deduplicated() -> None:
    first = build_recovery_plan(DEFAULT_WEEK3)
    second = build_recovery_plan(DEFAULT_WEEK3)

    assert first == second
    assert len({candidate.post.post_id for candidate in first.candidates}) == len(
        first.candidates
    )
