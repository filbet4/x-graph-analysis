"""Tests for translating domain data into a NetworkX multigraph.

TODO: Add graph serialization tests when a persistence format is selected.
"""

from datetime import UTC, datetime

import networkx as nx

from x_graph_analysis.domain.models import (
    Hashtag,
    Post,
    PostCollection,
    Relationship,
    RelationshipType,
    User,
)
from x_graph_analysis.graph.builder import NetworkXGraphBuilder

COLLECTED_AT = datetime(2026, 8, 1, 12, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 8, 1, 9, tzinfo=UTC)


def make_post(post_id: str, hashtags: tuple[str, ...] = ()) -> Post:
    """Create a small post with deterministic metadata for graph tests."""
    return Post(
        post_id=post_id,
        author=User(user_id=f"user-{post_id}", username=f"user_{post_id}"),
        text=f"Post {post_id}",
        published_at=PUBLISHED_AT,
        hashtags=tuple(
            Hashtag(text=hashtag, normalized_text=hashtag.casefold())
            for hashtag in hashtags
        ),
    )


def make_collection(*posts: Post) -> PostCollection:
    """Create a stable collection for graph tests."""
    return PostCollection(
        posts=posts,
        source_name="test",
        collected_at=COLLECTED_AT,
    )


def test_every_post_becomes_one_node_with_metadata() -> None:
    """All posts, including isolated posts, are represented exactly once."""
    collection = make_collection(
        make_post("post-a", ("Graphs",)),
        make_post("post-b"),
        make_post("post-c"),
    )

    graph = NetworkXGraphBuilder().build(collection, ())

    assert isinstance(graph, nx.MultiDiGraph)
    assert list(graph.nodes) == ["post-a", "post-b", "post-c"]
    assert graph.number_of_nodes() == len(collection.posts) == 3
    assert graph.degree("post-b") == 0
    assert graph.nodes["post-a"]["author_id"] == "user-post-a"
    assert graph.nodes["post-a"]["username"] == "user_post-a"
    assert graph.nodes["post-a"]["created_at"] == PUBLISHED_AT
    assert graph.nodes["post-a"]["hashtags"] == ("graphs",)


def test_directed_relationship_has_one_correctly_oriented_edge() -> None:
    """Directed domain relationships become one source-to-target edge."""
    collection = make_collection(make_post("source"), make_post("target"))
    relationship = Relationship(
        source_post_id="source",
        target_post_id="target",
        relationship_type=RelationshipType.REPLY,
        weight=1,
        directed=True,
    )

    graph = NetworkXGraphBuilder().build(collection, (relationship,))

    assert graph.number_of_edges() == 1
    assert graph.has_edge("source", "target")
    assert not graph.has_edge("target", "source")
    edge = graph["source"]["target"][0]
    assert edge["relationship_type"] is RelationshipType.REPLY
    assert edge["weight"] == 1
    assert edge["directed"] is True


def test_shared_hashtag_relationship_creates_symmetric_edges() -> None:
    """Undirected domain similarity is represented by two equivalent edges."""
    collection = make_collection(make_post("a"), make_post("b"))
    relationship = Relationship(
        source_post_id="a",
        target_post_id="b",
        relationship_type=RelationshipType.SHARED_HASHTAG,
        weight=2,
        directed=False,
        evidence_hashtags=(
            Hashtag(text="graphs", normalized_text="graphs"),
            Hashtag(text="networks", normalized_text="networks"),
        ),
    )

    graph = NetworkXGraphBuilder().build(collection, (relationship,))

    assert graph.number_of_edges() == 2
    forward = graph["a"]["b"][0]
    reverse = graph["b"]["a"][0]
    assert forward == reverse
    assert forward["relationship_type"] is RelationshipType.SHARED_HASHTAG
    assert forward["weight"] == 2
    assert forward["evidence_hashtags"] == relationship.evidence_hashtags
    assert forward["directed"] is False


def test_parallel_relationship_types_are_preserved() -> None:
    """MultiDiGraph retains distinct relationship types for one post pair."""
    collection = make_collection(make_post("a"), make_post("b"))
    relationships = (
        Relationship(
            source_post_id="a",
            target_post_id="b",
            relationship_type=RelationshipType.SHARED_HASHTAG,
            weight=1,
            directed=False,
        ),
        Relationship(
            source_post_id="a",
            target_post_id="b",
            relationship_type=RelationshipType.REPLY,
        ),
    )

    graph = NetworkXGraphBuilder().build(collection, relationships)

    assert graph.number_of_edges() == 3
    assert {graph["a"]["b"][key]["relationship_type"] for key in graph["a"]["b"]} == {
        RelationshipType.SHARED_HASHTAG,
        RelationshipType.REPLY,
    }
    assert graph.number_of_edges("b", "a") == 1


def test_empty_collection_produces_empty_graph() -> None:
    """An empty collection translates to an empty MultiDiGraph."""
    graph = NetworkXGraphBuilder().build(make_collection(), ())

    assert graph.number_of_nodes() == 0
    assert graph.number_of_edges() == 0


def test_graph_construction_is_deterministic() -> None:
    """Repeated construction preserves node, edge, and metadata ordering."""
    collection = make_collection(
        make_post("a"),
        make_post("b"),
        make_post("c"),
    )
    relationships = (
        Relationship("a", "b", RelationshipType.REPLY),
        Relationship("a", "b", RelationshipType.QUOTE),
        Relationship("b", "c", RelationshipType.REPOST),
    )
    builder = NetworkXGraphBuilder()

    first = builder.build(collection, relationships)
    second = builder.build(collection, relationships)

    assert list(first.nodes(data=True)) == list(second.nodes(data=True))
    assert list(first.edges(keys=True, data=True)) == list(
        second.edges(keys=True, data=True)
    )
