"""Tests for immutable domain entities and supported relationship types.

TODO: Add schema and serialization contract tests when persistence is introduced.
"""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from x_graph_analysis.domain.models import (
    Hashtag,
    Mention,
    Metrics,
    Post,
    PostCollection,
    Relationship,
    RelationshipType,
    User,
)


def test_entities_are_immutable() -> None:
    """Frozen entities reject reassignment after construction."""
    user = User(user_id="user-1", username="alice")

    with pytest.raises(FrozenInstanceError):
        user.username = "changed"  # type: ignore[misc]


def test_post_composes_all_post_level_entities() -> None:
    """A post can carry author, hashtags, mentions, and point-in-time metrics."""
    author = User(user_id="user-1", username="alice")
    mentioned_user = User(user_id="user-2", username="bob")
    post = Post(
        post_id="post-1",
        author=author,
        text="Hello #graphs @bob",
        published_at=datetime.now(UTC),
        hashtags=(Hashtag(text="graphs", normalized_text="graphs"),),
        mentions=(Mention(user=mentioned_user, username="bob"),),
        metrics=Metrics(like_count=3),
    )

    assert post.author == author
    assert post.hashtags[0].normalized_text == "graphs"
    assert post.mentions[0].user == mentioned_user
    assert post.metrics == Metrics(like_count=3)


def test_relationship_supports_all_declared_post_edge_types() -> None:
    """Every required relationship kind is representable without behavior."""
    relationships = tuple(
        Relationship(
            source_post_id="source",
            target_post_id="target",
            relationship_type=relationship_type,
            directed=relationship_type is not RelationshipType.SHARED_HASHTAG,
        )
        for relationship_type in RelationshipType
    )

    assert {relationship.relationship_type for relationship in relationships} == {
        RelationshipType.SHARED_HASHTAG,
        RelationshipType.REPLY,
        RelationshipType.QUOTE,
        RelationshipType.REPOST,
        RelationshipType.MENTION,
    }


@pytest.mark.parametrize(
    "factory",
    (
        lambda: User(user_id="", username="alice"),
        lambda: User(user_id="user-1", username=""),
        lambda: Post(
            post_id="post-1",
            author=User(user_id="user-1", username="alice"),
            text="text",
            published_at=datetime(2026, 1, 1),
        ),
        lambda: Metrics(like_count=-1),
        lambda: Relationship(
            source_post_id="same",
            target_post_id="same",
            relationship_type=RelationshipType.REPLY,
        ),
        lambda: Relationship(
            source_post_id="source",
            target_post_id="target",
            relationship_type=RelationshipType.REPLY,
            weight=0,
        ),
        lambda: Relationship(
            source_post_id="source",
            target_post_id="target",
            relationship_type=RelationshipType.SHARED_HASHTAG,
        ),
    ),
)
def test_invalid_domain_states_are_rejected(factory: object) -> None:
    """Clearly invalid entity values fail at construction time."""
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]


def test_post_collection_rejects_duplicate_post_ids() -> None:
    """Duplicate IDs cannot reach graph construction."""
    author = User(user_id="user-1", username="alice")
    post = Post(
        post_id="post-1",
        author=author,
        text="text",
        published_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match="post IDs must be unique"):
        PostCollection(
            posts=(post, post),
            source_name="test",
            collected_at=datetime.now(UTC),
        )
