"""Tests for deterministic relationship detection over post collections.

TODO: Add property-based tests when relationship semantics stabilize.
"""

from datetime import UTC, datetime

from x_graph_analysis.domain.models import (
    Hashtag,
    Mention,
    Post,
    PostCollection,
    RelationshipType,
    User,
)
from x_graph_analysis.graph.builder import RelationshipBuilder

COLLECTED_AT = datetime(2026, 8, 1, 12, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 8, 1, 9, tzinfo=UTC)


def make_post(
    post_id: str,
    hashtags: tuple[str, ...] = (),
    *,
    reply_to: str | None = None,
    quote: str | None = None,
    repost: str | None = None,
    mentions: tuple[str, ...] = (),
) -> Post:
    """Create a small domain post for relationship tests."""
    author = User(user_id=f"user-{post_id}", username=f"user_{post_id}")
    return Post(
        post_id=post_id,
        author=author,
        text=f"Post {post_id}",
        published_at=PUBLISHED_AT,
        hashtags=tuple(
            Hashtag(text=hashtag, normalized_text=hashtag.casefold())
            for hashtag in hashtags
        ),
        mentions=tuple(
            Mention(
                user=User(user_id=f"mentioned-{username}", username=username),
                username=username,
            )
            for username in mentions
        ),
        reply_to_post_id=reply_to,
        quoted_post_id=quote,
        reposted_post_id=repost,
    )


def make_collection(*posts: Post) -> PostCollection:
    """Create a collection with a stable source and collection timestamp."""
    return PostCollection(
        posts=posts,
        source_name="test",
        collected_at=COLLECTED_AT,
    )


def test_detects_one_shared_hashtag_as_undirected_relationship() -> None:
    """One common normalized hashtag produces one weighted similarity edge."""
    relationships = RelationshipBuilder().build(
        make_collection(
            make_post("a", ("Graphs",)),
            make_post("b", ("graphs",)),
        )
    )

    assert len(relationships) == 1
    relationship = relationships[0]
    assert relationship.relationship_type is RelationshipType.SHARED_HASHTAG
    assert relationship.source_post_id == "a"
    assert relationship.target_post_id == "b"
    assert relationship.directed is False
    assert relationship.weight == 1
    assert relationship.evidence_hashtags == (
        Hashtag(text="Graphs", normalized_text="graphs"),
    )


def test_detects_multiple_shared_hashtags_with_matching_weight() -> None:
    """All shared normalized hashtags are retained as evidence."""
    relationships = RelationshipBuilder().build(
        make_collection(
            make_post("a", ("graphs", "Networks", "unique-a")),
            make_post("b", ("networks", "graphs", "unique-b")),
        )
    )

    assert len(relationships) == 1
    assert relationships[0].weight == 2
    assert relationships[0].evidence_hashtags == (
        Hashtag(text="graphs", normalized_text="graphs"),
        Hashtag(text="Networks", normalized_text="networks"),
    )


def test_does_not_detect_posts_without_shared_hashtags() -> None:
    """Different hashtag sets do not produce a similarity relationship."""
    relationships = RelationshipBuilder().build(
        make_collection(
            make_post("a", ("graphs",)),
            make_post("b", ("networks",)),
        )
    )

    assert relationships == ()


def test_shared_hashtag_relationship_is_not_emitted_in_reverse() -> None:
    """The unordered pair appears only once, in collection order."""
    relationships = RelationshipBuilder().build(
        make_collection(
            make_post("b", ("graphs",)),
            make_post("a", ("graphs",)),
        )
    )

    assert [(item.source_post_id, item.target_post_id) for item in relationships] == [
        ("b", "a")
    ]


def test_detects_reply_quote_and_repost_as_directed_edges() -> None:
    """Direct post references create directed interactions to in-collection posts."""
    relationships = RelationshipBuilder().build(
        make_collection(
            make_post("target"),
            make_post("reply", reply_to="target"),
            make_post("quote", quote="target"),
            make_post("repost", repost="target"),
        )
    )

    assert [relationship.relationship_type for relationship in relationships] == [
        RelationshipType.REPLY,
        RelationshipType.QUOTE,
        RelationshipType.REPOST,
    ]
    assert all(relationship.directed for relationship in relationships)
    assert all(relationship.weight == 1 for relationship in relationships)
    assert [(item.source_post_id, item.target_post_id) for item in relationships] == [
        ("reply", "target"),
        ("quote", "target"),
        ("repost", "target"),
    ]


def test_ignores_references_to_posts_outside_collection() -> None:
    """A dangling reply, quote, or repost does not create an edge."""
    relationships = RelationshipBuilder().build(
        make_collection(
            make_post("source", reply_to="missing", quote="missing", repost="missing"),
        )
    )

    assert relationships == ()


def test_post_never_creates_relationship_with_itself() -> None:
    """Self-references and self-similarity are excluded."""
    relationships = RelationshipBuilder().build(
        make_collection(make_post("same", ("graphs",), reply_to="same"))
    )

    assert relationships == ()


def test_empty_collection_produces_no_relationships() -> None:
    """An empty collection is a valid no-op input."""
    assert RelationshipBuilder().build(make_collection()) == ()


def test_mentions_do_not_create_post_relationships() -> None:
    """Mentions target users, not posts, so no post edge is inferred."""
    relationships = RelationshipBuilder().build(
        make_collection(make_post("source", mentions=("target-user",)))
    )

    assert relationships == ()
