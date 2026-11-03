"""Translate domain posts and relationships into a NetworkX multigraph.

TODO: Add graph serialization and graph metadata once persistence requirements
are defined. Relationship detection remains owned by ``RelationshipBuilder``.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import networkx as nx

from x_graph_analysis.domain.models import (
    Hashtag,
    Post,
    PostCollection,
    Relationship,
    RelationshipType,
)
from x_graph_analysis.domain.ports import GraphBuilder


class RelationshipBuilder:
    """Build explicit relationships from posts in one collection."""

    def build(self, collection: PostCollection) -> tuple[Relationship, ...]:
        """Detect shared-hashtag and direct post-reference relationships."""
        posts = collection.posts
        relationships = list(self._shared_hashtag_relationships(posts))
        relationships.extend(self._direct_relationships(posts))
        return tuple(relationships)

    @staticmethod
    def _shared_hashtag_relationships(
        posts: tuple[Post, ...],
    ) -> Iterable[Relationship]:
        hashtag_index: dict[str, list[int]] = {}
        hashtags_by_post: list[dict[str, Hashtag]] = []
        for post_index, post in enumerate(posts):
            hashtags = RelationshipBuilder._unique_hashtags(post)
            hashtags_by_post.append(hashtags)
            for normalized_text in hashtags:
                hashtag_index.setdefault(normalized_text, []).append(post_index)

        shared_by_pair: dict[tuple[int, int], set[str]] = {}
        for normalized_text, post_indices in hashtag_index.items():
            for left_offset, left_index in enumerate(post_indices):
                for right_index in post_indices[left_offset + 1 :]:
                    shared_by_pair.setdefault((left_index, right_index), set()).add(
                        normalized_text
                    )

        for left_index, right_index in sorted(shared_by_pair):
            shared_names = shared_by_pair[(left_index, right_index)]
            evidence = tuple(
                hashtag
                for normalized_text, hashtag in hashtags_by_post[left_index].items()
                if normalized_text in shared_names
            )
            yield Relationship(
                source_post_id=posts[left_index].post_id,
                target_post_id=posts[right_index].post_id,
                relationship_type=RelationshipType.SHARED_HASHTAG,
                weight=len(evidence),
                directed=False,
                evidence_hashtags=evidence,
            )

    @staticmethod
    def _direct_relationships(posts: tuple[Post, ...]) -> Iterable[Relationship]:
        post_ids = {post.post_id for post in posts}
        for post in posts:
            references = (
                (post.reply_to_post_id, RelationshipType.REPLY),
                (post.quoted_post_id, RelationshipType.QUOTE),
                (post.reposted_post_id, RelationshipType.REPOST),
            )
            for target_post_id, relationship_type in references:
                if (
                    target_post_id is not None
                    and target_post_id in post_ids
                    and target_post_id != post.post_id
                ):
                    yield Relationship(
                        source_post_id=post.post_id,
                        target_post_id=target_post_id,
                        relationship_type=relationship_type,
                    )

    @staticmethod
    def _unique_hashtags(post: Post) -> dict[str, Hashtag]:
        unique_hashtags: dict[str, Hashtag] = {}
        for hashtag in post.hashtags:
            unique_hashtags.setdefault(hashtag.normalized_text, hashtag)
        return unique_hashtags


class NetworkXGraphBuilder(GraphBuilder):
    """Build a deterministic ``networkx.MultiDiGraph`` from domain data."""

    def build(
        self,
        collection: PostCollection,
        relationships: Sequence[Relationship],
    ) -> nx.MultiDiGraph[Any, Any]:
        """Translate posts to nodes and supplied relationships to edges."""
        graph: nx.MultiDiGraph[Any, Any] = nx.MultiDiGraph()
        for post in collection.posts:
            graph.add_node(post.post_id, **self._node_attributes(post))

        post_ids = set(graph.nodes)
        for relationship in relationships:
            self._add_relationship(graph, relationship, post_ids)

        return graph

    @staticmethod
    def _node_attributes(post: Post) -> dict[str, Any]:
        return {
            "author_id": post.author.user_id,
            "username": post.author.username,
            "created_at": post.published_at,
            "hashtags": tuple(hashtag.normalized_text for hashtag in post.hashtags),
            "text": post.text,
        }

    @classmethod
    def _add_relationship(
        cls,
        graph: nx.MultiDiGraph[Any, Any],
        relationship: Relationship,
        post_ids: set[str],
    ) -> None:
        endpoints = {
            relationship.source_post_id,
            relationship.target_post_id,
        }
        if not endpoints.issubset(post_ids):
            raise ValueError(
                "Relationship endpoints must refer to posts in the collection"
            )

        attributes = cls._edge_attributes(relationship)
        graph.add_edge(
            relationship.source_post_id,
            relationship.target_post_id,
            **attributes,
        )
        if relationship.relationship_type is RelationshipType.SHARED_HASHTAG:
            graph.add_edge(
                relationship.target_post_id,
                relationship.source_post_id,
                **attributes,
            )

    @staticmethod
    def _edge_attributes(relationship: Relationship) -> dict[str, Any]:
        return {
            "relationship_type": relationship.relationship_type,
            "weight": relationship.weight,
            "evidence_hashtags": relationship.evidence_hashtags,
            "directed": relationship.directed,
            "observed_at": relationship.observed_at,
        }


# TODO: Remove this compatibility alias after downstream callers migrate.
RelationshipGraphBuilder = NetworkXGraphBuilder
