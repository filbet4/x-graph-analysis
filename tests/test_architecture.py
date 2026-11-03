"""Initial contract tests proving the project skeleton is importable.

TODO: Add focused tests for each implemented adapter, stage, and use case.
"""

from datetime import UTC, datetime

from x_graph_analysis.adapters.sources.x_platform import XPlatformSource
from x_graph_analysis.domain.models import Post, PostCollection, User


def test_post_model_is_source_independent() -> None:
    """The core post model can be created without an external API dependency."""
    author = User(user_id="author-1", username="researcher")
    post = Post(
        post_id="post-1",
        author=author,
        text="placeholder",
        published_at=datetime.now(UTC),
    )

    collection = PostCollection(
        posts=(post,),
        source_name="test",
        collected_at=datetime.now(UTC),
    )

    assert collection.posts == (post,)


def test_x_platform_adapter_exposes_source_identity() -> None:
    """The future adapter satisfies the source identity portion of its port."""
    assert XPlatformSource().name == "x-platform"
