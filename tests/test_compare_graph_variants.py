"""Tests for the three local graph variant projections."""

from datetime import UTC, datetime

import networkx as nx
from experiments.compare_graph_variants import (
    graph_metrics,
    heterogeneous_graph,
    interaction_coverage,
    user_graph,
)

from x_graph_analysis.domain.models import (
    Hashtag,
    Post,
    Relationship,
    RelationshipType,
    User,
)

TIME = datetime(2026, 10, 21, tzinfo=UTC)


def make_posts() -> dict[str, Post]:
    user_a = User(user_id="a", username="alice")
    user_b = User(user_id="b", username="bob")
    return {
        "post-a": Post(
            post_id="post-a",
            author=user_a,
            text="A #topic",
            published_at=TIME,
            hashtags=(Hashtag(text="topic", normalized_text="topic"),),
            reply_to_post_id="post-b",
        ),
        "post-b": Post(
            post_id="post-b",
            author=user_b,
            text="B #topic",
            published_at=TIME,
            hashtags=(Hashtag(text="topic", normalized_text="topic"),),
        ),
    }


def test_user_projection_uses_interactions_not_shared_hashtags() -> None:
    posts = make_posts()
    relationships = (
        Relationship(
            source_post_id="post-a",
            target_post_id="post-b",
            relationship_type=RelationshipType.REPLY,
        ),
    )

    graph = user_graph(posts, relationships)

    assert set(graph.nodes) == {"a", "b"}
    assert graph.number_of_edges() == 1
    assert graph["a"]["b"][0]["relationship_type"] == "reply"
    assert graph["a"]["b"][0]["weight"] == 1


def test_heterogeneous_graph_has_user_post_hashtag_and_interaction_edges() -> None:
    posts = make_posts()
    relationships = (
        Relationship(
            source_post_id="post-a",
            target_post_id="post-b",
            relationship_type=RelationshipType.REPLY,
        ),
    )

    graph = heterogeneous_graph(posts, set(posts), relationships)

    assert graph.nodes["user:a"]["node_type"] == "User"
    assert graph.nodes["post:post-a"]["node_type"] == "Post"
    assert graph.nodes["hashtag:topic"]["node_type"] == "Hashtag"
    assert graph.has_edge("user:a", "post:post-a")
    assert graph.has_edge("post:post-a", "hashtag:topic")
    assert graph.has_edge("post:post-a", "post:post-b")
    assert all(
        data["relationship_type"] != "SHARED_HASHTAG"
        for _, _, data in graph.edges(data=True)
    )


def test_coverage_reports_missing_targets_without_creating_edges() -> None:
    posts = make_posts()
    coverage = interaction_coverage(posts, {"post-a"})

    assert coverage["reply_references"] == 1
    assert coverage["missing_reply_targets"] == 1
    assert coverage["quote_references"] == 0


def test_graph_metrics_include_components_and_pagerank() -> None:
    graph = nx.MultiDiGraph()
    graph.add_edge("a", "b", weight=2)
    graph.add_node("c")

    metrics = graph_metrics(graph)

    assert metrics["node_count"] == 3
    assert metrics["edge_count"] == 1
    assert metrics["weighted_interaction_count"] == 2
    assert metrics["weak_component_count"] == 2
    assert metrics["top_pagerank"]
