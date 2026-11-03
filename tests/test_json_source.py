"""Tests for the local JSON post source adapter.

TODO: Add compatibility tests when the persisted input schema is versioned.
"""

from pathlib import Path

import pytest

from x_graph_analysis.adapters.sources.json_file import (
    JsonDataSourceError,
    LocalJsonPostSource,
)
from x_graph_analysis.domain.models import Metrics

SAMPLE_FILE = Path(__file__).parents[1] / "data" / "sample_posts.json"


def test_loads_sample_json_file() -> None:
    """The fictional sample dataset loads as a complete post collection."""
    collection = LocalJsonPostSource(SAMPLE_FILE).collect()

    assert collection.source_name == "local-json"
    assert len(collection.posts) == 15
    assert collection.posts[0].post_id == "post-001"
    assert collection.posts[0].author.username == "aurora_field"


def test_maps_nested_entities_and_post_references() -> None:
    """Nested JSON values map to domain entities without adapter leakage."""
    posts = LocalJsonPostSource(SAMPLE_FILE).collect().posts

    quoted_post = posts[2]
    replied_post = posts[7]
    mentioned_post = posts[4]

    assert quoted_post.quoted_post_id == "post-001"
    assert replied_post.reply_to_post_id == "post-007"
    assert mentioned_post.mentions[0].user.username == "aurora_field"
    assert posts[0].hashtags[0].normalized_text == "graphresearch"
    assert posts[0].metrics == Metrics(
        like_count=42,
        repost_count=8,
        reply_count=5,
        quote_count=2,
        view_count=1200,
    )


def test_missing_optional_fields_use_domain_defaults() -> None:
    """Records without optional content remain valid domain posts."""
    posts = LocalJsonPostSource(SAMPLE_FILE).collect().posts

    post_without_optional_fields = posts[5]

    assert post_without_optional_fields.hashtags == ()
    assert post_without_optional_fields.mentions == ()
    assert post_without_optional_fields.metrics is None
    assert post_without_optional_fields.reply_to_post_id is None
    assert post_without_optional_fields.quoted_post_id is None
    assert post_without_optional_fields.reposted_post_id is None
    assert post_without_optional_fields.author.verified is False


def test_missing_normalized_hashtag_text_is_derived_as_mapping_default(
    tmp_path: Path,
) -> None:
    """A missing optional hashtag normalization uses the visible hashtag text."""
    input_file = tmp_path / "posts.json"
    input_file.write_text(
        '[{"post_id": "post-1", "author": '
        '{"user_id": "user-1", "username": "alice"}, '
        '"text": "#Graphs", "published_at": '
        '"2026-08-01T09:00:00Z", '
        '"hashtags": [{"text": "Graphs"}]}]',
        encoding="utf-8",
    )

    post = LocalJsonPostSource(input_file).collect().posts[0]

    assert post.hashtags[0].normalized_text == "graphs"


@pytest.mark.parametrize(
    ("contents", "error_text"),
    [
        ('{"post_id": "post-1"}', "root must be an array"),
        ('[{"post_id": "post-1"}]', "author"),
        (
            '[{"post_id": "post-1", "author": '
            '{"user_id": "user-1", "username": "alice"}, '
            '"text": "text", "published_at": "not-a-date"}]',
            "published_at",
        ),
        (
            '[{"post_id": "post-1", "author": {}, '
            '"text": "text", "published_at": "2026-08-01T09:00:00Z", '
            '"metrics": {"like_count": "many"}}]',
            "user_id",
        ),
    ],
)
def test_invalid_input_raises_adapter_error(
    tmp_path: Path,
    contents: str,
    error_text: str,
) -> None:
    """Malformed JSON shape and invalid field values fail clearly."""
    input_file = tmp_path / "invalid.json"
    input_file.write_text(contents, encoding="utf-8")

    with pytest.raises(JsonDataSourceError, match=error_text):
        LocalJsonPostSource(input_file).collect()


def test_malformed_json_raises_adapter_error(tmp_path: Path) -> None:
    """Unreadable JSON is translated into the adapter's public error."""
    input_file = tmp_path / "malformed.json"
    input_file.write_text("not json", encoding="utf-8")

    with pytest.raises(JsonDataSourceError, match="Unable to read valid JSON"):
        LocalJsonPostSource(input_file).collect()
