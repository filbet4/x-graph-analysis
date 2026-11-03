"""Immutable source-independent entities used by the analysis pipeline.

TODO: Refine field types and identifiers when the approved dataset schema is
defined. This module intentionally contains data declarations only.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class User:
    """A source-independent representation of an X account."""

    user_id: str
    username: str
    display_name: str | None = None
    verified: bool = False

    def __post_init__(self) -> None:
        """Reject missing account identity values."""
        if not self.user_id:
            raise ValueError("user_id must be non-empty")
        if not self.username:
            raise ValueError("username must be non-empty")


@dataclass(frozen=True, slots=True)
class Hashtag:
    """A hashtag attached to a post."""

    text: str
    normalized_text: str


@dataclass(frozen=True, slots=True)
class Mention:
    """A mention of a user contained in a post."""

    user: User
    username: str
    start_offset: int | None = None
    end_offset: int | None = None


@dataclass(frozen=True, slots=True)
class Metrics:
    """Engagement metrics captured for a post at collection time."""

    like_count: int = 0
    repost_count: int = 0
    reply_count: int = 0
    quote_count: int = 0
    view_count: int | None = None

    def __post_init__(self) -> None:
        """Reject negative engagement counts."""
        counts = {
            "like_count": self.like_count,
            "repost_count": self.repost_count,
            "reply_count": self.reply_count,
            "quote_count": self.quote_count,
            "view_count": self.view_count,
        }
        for name, count in counts.items():
            if count is not None and count < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class Post:
    """A source-independent representation of a social media post."""

    post_id: str
    author: User
    text: str
    published_at: datetime
    hashtags: tuple[Hashtag, ...] = ()
    mentions: tuple[Mention, ...] = ()
    metrics: Metrics | None = None
    reply_to_post_id: str | None = None
    quoted_post_id: str | None = None
    reposted_post_id: str | None = None

    def __post_init__(self) -> None:
        """Reject missing post identity and naive publication timestamps."""
        if not self.post_id:
            raise ValueError("post_id must be non-empty")
        if self.published_at.tzinfo is None or self.published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")


class RelationshipType(StrEnum):
    """Supported meanings of a directed relationship between two posts."""

    SHARED_HASHTAG = "shared_hashtag"
    REPLY = "reply"
    QUOTE = "quote"
    REPOST = "repost"
    MENTION = "mention"


@dataclass(frozen=True, slots=True)
class Relationship:
    """A typed relationship between two posts.

    ``source_post_id`` is the post that expresses or contains the relationship,
    and ``target_post_id`` is the post it points to for directed relationships.
    Shared hashtag edges use the two IDs as a deterministic pair and set
    ``directed`` to ``False``. Shared hashtag edges may include the hashtags
    that provide their evidence.
    """

    source_post_id: str
    target_post_id: str
    relationship_type: RelationshipType
    weight: int = 1
    directed: bool = True
    observed_at: datetime | None = None
    evidence_hashtags: tuple[Hashtag, ...] = ()

    def __post_init__(self) -> None:
        """Enforce relationship identity, weight, and direction invariants."""
        if not self.source_post_id:
            raise ValueError("source_post_id must be non-empty")
        if not self.target_post_id:
            raise ValueError("target_post_id must be non-empty")
        if self.source_post_id == self.target_post_id:
            raise ValueError("source_post_id and target_post_id must differ")
        if self.weight <= 0:
            raise ValueError("weight must be greater than 0")
        expected_directed = (
            self.relationship_type is not RelationshipType.SHARED_HASHTAG
        )
        if self.directed != expected_directed:
            expected = "directed" if expected_directed else "undirected"
            raise ValueError(
                f"{self.relationship_type.value} relationships must be {expected}"
            )


@dataclass(frozen=True, slots=True)
class PostCollection:
    """A batch of posts returned by a data source."""

    posts: tuple[Post, ...]
    source_name: str
    collected_at: datetime

    def __post_init__(self) -> None:
        """Reject duplicate post identifiers before graph construction."""
        post_ids = [post.post_id for post in self.posts]
        if len(post_ids) != len(set(post_ids)):
            raise ValueError("post IDs must be unique")
