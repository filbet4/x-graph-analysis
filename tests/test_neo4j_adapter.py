"""Tests for the Neo4j persistence adapter."""

from datetime import UTC
from unittest.mock import MagicMock, patch

from x_graph_analysis.adapters.persistence.neo4j import Neo4jGraphRepository


@patch("x_graph_analysis.adapters.persistence.neo4j.GraphDatabase.driver")
def test_verify_connectivity(mock_driver_factory: MagicMock) -> None:
    """Repository delegates connectivity verification to the driver."""
    driver = MagicMock()
    mock_driver_factory.return_value = driver

    repository = Neo4jGraphRepository(
        uri="neo4j://localhost:7687",
        user="neo4j",
        password="secret",
        database="xgraph",
    )

    repository.verify_connectivity()

    driver.verify_connectivity.assert_called_once_with()


@patch("x_graph_analysis.adapters.persistence.neo4j.GraphDatabase.driver")
def test_close(mock_driver_factory: MagicMock) -> None:
    """Repository closes the underlying driver."""
    driver = MagicMock()
    mock_driver_factory.return_value = driver

    repository = Neo4jGraphRepository(
        uri="neo4j://localhost:7687",
        user="neo4j",
        password="secret",
        database="xgraph",
    )

    repository.close()

    driver.close.assert_called_once_with()


@patch("x_graph_analysis.adapters.persistence.neo4j.GraphDatabase.driver")
def test_create_constraints(mock_driver_factory: MagicMock) -> None:
    """Repository creates all required uniqueness constraints."""
    driver = MagicMock()
    session = MagicMock()

    driver.session.return_value.__enter__.return_value = session
    mock_driver_factory.return_value = driver

    repository = Neo4jGraphRepository(
        uri="neo4j://localhost:7687",
        user="neo4j",
        password="secret",
        database="xgraph",
    )

    repository.create_constraints()

    driver.session.assert_called_once_with(database="xgraph")
    assert session.run.call_count == 3

    queries = [
        call.args[0]
        for call in session.run.call_args_list
    ]

    assert any("post_id_unique" in query for query in queries)
    assert any("user_id_unique" in query for query in queries)
    assert any(
        "hashtag_normalized_text_unique" in query
        for query in queries
    )

def test_save_posts() -> None:
    """Repository persists posts in batches."""
    from datetime import datetime
    from unittest.mock import MagicMock, patch

    from x_graph_analysis.domain.models import (
        Hashtag,
        Metrics,
        Post,
        User,
    )

    user = User(
        user_id="user-1",
        username="test_user",
        display_name="Test User",
        verified=True,
    )

    post = Post(
        post_id="post-1",
        author=user,
        text="Test post #Python",
        published_at=datetime(
            2026,
            10,
            10,
            12,
            0,
            tzinfo=UTC,
        ),
        hashtags=(
            Hashtag(
                text="Python",
                normalized_text="python",
            ),
        ),
        metrics=Metrics(
            like_count=10,
            repost_count=2,
            reply_count=3,
            quote_count=1,
            view_count=100,
        ),
    )

    with patch(
        "x_graph_analysis.adapters.persistence.neo4j."
        "GraphDatabase.driver"
    ) as driver_factory:
        driver = MagicMock()
        session = MagicMock()

        driver_factory.return_value = driver
        driver.session.return_value.__enter__.return_value = session

        repository = Neo4jGraphRepository(
            uri="neo4j://localhost:7687",
            user="neo4j",
            password="secret",
            database="xgraph",
        )

        repository.save_posts([post])

        driver.session.assert_called_once_with(
            database="xgraph"
        )
        session.run.assert_called_once()

        _, kwargs = session.run.call_args

        assert len(kwargs["posts"]) == 1

        row = kwargs["posts"][0]

        assert row["post_id"] == "post-1"
        assert row["author"]["user_id"] == "user-1"
        assert row["author"]["username"] == "test_user"
        assert row["like_count"] == 10
        assert row["view_count"] == 100
        assert row["hashtags"] == [
            {
                "text": "Python",
                "normalized_text": "python",
            }
        ]

def test_save_post_relationships() -> None:
    """Repository persists directed post relationships."""
    with patch(
        "x_graph_analysis.adapters.persistence.neo4j."
        "GraphDatabase.driver"
    ) as driver_factory:
        driver = MagicMock()
        session = MagicMock()

        driver_factory.return_value = driver
        driver.session.return_value.__enter__.return_value = session

        repository = Neo4jGraphRepository(
            uri="neo4j://localhost:7687",
            user="neo4j",
            password="secret",
            database="xgraph",
        )

        relationships = [
            {
                "source_post_id": "post-1",
                "target_post_id": "post-2",
                "type": "REPLY",
            },
            {
                "source_post_id": "post-3",
                "target_post_id": "post-4",
                "type": "QUOTE",
            },
        ]

        repository.save_post_relationships(relationships)

        driver.session.assert_called_once_with(database="xgraph")
        assert session.run.call_count == 2

        saved_rows = [
            call.kwargs["relationships"][0]
            for call in session.run.call_args_list
        ]

        assert {
            (
                row["source_post_id"],
                row["target_post_id"],
                row["type"],
            )
            for row in saved_rows
        } == {
            ("post-1", "post-2", "REPLY"),
            ("post-3", "post-4", "QUOTE"),
        }