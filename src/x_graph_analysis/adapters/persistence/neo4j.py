"""Neo4j persistence adapter."""

from neo4j import Driver, GraphDatabase

from x_graph_analysis.domain.models import Post


class Neo4jGraphRepository:
    """Persist graph data in a Neo4j database."""

    def __init__(
        self,
        uri: str,
        user: str,
        password: str,
        database: str,
    ) -> None:
        """Create a Neo4j repository."""
        self._driver: Driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
        )
        self._database = database

    def verify_connectivity(self) -> None:
        """Verify that the Neo4j server is reachable."""
        self._driver.verify_connectivity()

    def close(self) -> None:
        """Close the Neo4j driver."""
        self._driver.close()

    def create_constraints(self) -> None:
        """Create uniqueness constraints required by the graph model."""
        queries = (
            """
            CREATE CONSTRAINT post_id_unique IF NOT EXISTS
            FOR (post:Post)
            REQUIRE post.post_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT user_id_unique IF NOT EXISTS
            FOR (user:User)
            REQUIRE user.user_id IS UNIQUE
            """,
            """
            CREATE CONSTRAINT hashtag_normalized_text_unique IF NOT EXISTS
            FOR (hashtag:Hashtag)
            REQUIRE hashtag.normalized_text IS UNIQUE
            """,
        )

        with self._driver.session(database=self._database) as session:
            for query in queries:
                session.run(query).consume()

    def save_posts(
        self,
        posts: list[Post],
        batch_size: int = 500,
    ) -> None:
        """Persist posts and their structural nodes in batches."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        rows = [self._post_to_row(post) for post in posts]

        with self._driver.session(database=self._database) as session:
            for start in range(0, len(rows), batch_size):
                batch = rows[start : start + batch_size]

                session.run(
                    """
                    UNWIND $posts AS row

                    MERGE (user:User {user_id: row.author.user_id})
                    SET user.username = row.author.username,
                        user.display_name = row.author.display_name,
                        user.verified = row.author.verified

                    MERGE (post:Post {post_id: row.post_id})
                    SET post.text = row.text,
                        post.published_at = row.published_at,
                        post.like_count = row.like_count,
                        post.repost_count = row.repost_count,
                        post.reply_count = row.reply_count,
                        post.quote_count = row.quote_count,
                        post.view_count = row.view_count

                    MERGE (user)-[:AUTHORED]->(post)

                    WITH post, row
                    UNWIND row.hashtags AS hashtag_data

                    MERGE (hashtag:Hashtag {
                        normalized_text: hashtag_data.normalized_text
                    })
                    ON CREATE SET hashtag.text = hashtag_data.text

                    MERGE (post)-[:HAS_HASHTAG]->(hashtag)
                    """,
                    posts=batch,
                ).consume()

    @staticmethod
    def _post_to_row(post: Post) -> dict[str, object]:
        """Convert a domain post to Neo4j-compatible parameters."""
        metrics = post.metrics

        return {
            "post_id": post.post_id,
            "author": {
                "user_id": post.author.user_id,
                "username": post.author.username,
                "display_name": post.author.display_name,
                "verified": post.author.verified,
            },
            "text": post.text,
            "published_at": post.published_at,
            "like_count": (
                metrics.like_count
                if metrics is not None
                else 0
            ),
            "repost_count": (
                metrics.repost_count
                if metrics is not None
                else 0
            ),
            "reply_count": (
                metrics.reply_count
                if metrics is not None
                else 0
            ),
            "quote_count": (
                metrics.quote_count
                if metrics is not None
                else 0
            ),
            "view_count": (
                metrics.view_count
                if metrics is not None
                else None
            ),
            "hashtags": [
                {
                    "text": hashtag.text,
                    "normalized_text": hashtag.normalized_text,
                }
                for hashtag in post.hashtags
            ],
        }

    def save_post_relationships(
    self,
    relationships: list[dict[str, str]],
    batch_size: int = 500,
    ) -> None:
        """Persist directed relationships between posts."""
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")

        allowed_types = {"REPLY", "QUOTE", "REPOST"}

        with self._driver.session(database=self._database) as session:
            for start in range(0, len(relationships), batch_size):
                batch = relationships[start : start + batch_size]

                for relationship_type in allowed_types:
                    rows = [
                        row
                        for row in batch
                        if row["type"] == relationship_type
                    ]

                    if not rows:
                        continue

                    session.run(
                        f"""
                        UNWIND $relationships AS row
                        MATCH (source:Post {{post_id: row.source_post_id}})
                        MATCH (target:Post {{post_id: row.target_post_id}})
                        MERGE (source)-[:{relationship_type}]->(target)
                        """,
                        relationships=rows,
                    ).consume()

    def set_post_origins(
    self,
    seed_post_ids: list[str],
    target_post_ids: list[str],
) -> None:
        """Set dataset origin for Search seeds and one-hop targets."""
        with self._driver.session(database=self._database) as session:
            session.run(
                """
                UNWIND $post_ids AS post_id
                MATCH (post:Post {post_id: post_id})
                SET post.origin = 'SEARCH_SEED'
                """,
                post_ids=seed_post_ids,
            ).consume()

            session.run(
                """
                UNWIND $post_ids AS post_id
                MATCH (post:Post {post_id: post_id})
                WHERE post.origin IS NULL
                SET post.origin = 'ONE_HOP_TARGET'
                """,
                post_ids=target_post_ids,
            ).consume()