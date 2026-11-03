"""Structural analysis of the existing NetworkX multigraph.

TODO: Add further analysis result fields only when their methodology is
specified. This module must not detect relationships or mutate the graph.
"""

from __future__ import annotations

import math
from collections.abc import Collection
from dataclasses import dataclass
from numbers import Real
from typing import Any, cast

import networkx as nx

from x_graph_analysis.domain.models import RelationshipType
from x_graph_analysis.domain.ports import GraphAnalyzer


@dataclass(frozen=True, slots=True)
class GraphStatistics:
    """Basic statistics calculated from the master multigraph."""

    node_count: int
    edge_count: int
    density: float
    isolated_node_count: int


@dataclass(frozen=True, slots=True)
class NodeMetrics:
    """Degree and path-based centrality metrics for one graph node."""

    node_id: str
    degree: int
    in_degree: int
    out_degree: int
    degree_centrality: float
    in_degree_centrality: float
    out_degree_centrality: float
    betweenness_centrality: float
    closeness_centrality: float


@dataclass(frozen=True, slots=True)
class ComponentMembership:
    """Stable component identifiers for one graph node."""

    node_id: str
    weak_component_id: int
    strong_component_id: int


@dataclass(frozen=True, slots=True)
class PageRankScore:
    """PageRank score for one graph node."""

    node_id: str
    score: float


@dataclass(frozen=True, slots=True)
class ClusteringCoefficient:
    """Local undirected clustering coefficient for one graph node."""

    node_id: str
    coefficient: float


@dataclass(frozen=True, slots=True)
class Community:
    """One deterministically identified Louvain community."""

    community_id: int
    members: tuple[str, ...]
    size: int


@dataclass(frozen=True, slots=True)
class CommunityMembership:
    """The community assigned to one graph node."""

    node_id: str
    community_id: int


@dataclass(frozen=True, slots=True)
class CommunityDetectionResult:
    """Immutable Louvain communities and node assignments."""

    communities: tuple[Community, ...]
    memberships: tuple[CommunityMembership, ...]
    community_count: int


@dataclass(frozen=True, slots=True)
class CommunityStructuralMetrics:
    """Structural statistics for one detected community."""

    community_id: int
    node_count: int
    internal_edge_count: int
    internal_density: float
    average_clustering: float


@dataclass(frozen=True, slots=True)
class GraphAnalysisResult:
    """Complete structural analysis result in deterministic node order."""

    statistics: GraphStatistics
    node_metrics: tuple[NodeMetrics, ...]
    weakly_connected_components: tuple[tuple[str, ...], ...]
    strongly_connected_components: tuple[tuple[str, ...], ...]
    component_membership: tuple[ComponentMembership, ...]
    pagerank: tuple[PageRankScore, ...]
    communities: CommunityDetectionResult
    clustering_coefficients: tuple[ClusteringCoefficient, ...]
    average_clustering: float
    transitivity: float
    community_metrics: tuple[CommunityStructuralMetrics, ...]
    relationship_types: tuple[RelationshipType, ...] | None


class NetworkAnalyzer(GraphAnalyzer):
    """Calculate structural metrics without changing the input graph."""

    def __init__(
        self,
        alpha: float = 0.85,
        resolution: float = 1.0,
        seed: int = 42,
    ) -> None:
        """Create an analyzer with configurable PageRank and Louvain settings."""
        if isinstance(alpha, bool) or not isinstance(alpha, Real):
            raise TypeError("alpha must be a real number")
        if not math.isfinite(alpha) or not 0.0 < alpha <= 1.0:
            raise ValueError("alpha must be finite and satisfy 0 < alpha <= 1")
        if isinstance(resolution, bool) or not isinstance(resolution, Real):
            raise TypeError("resolution must be a real number")
        if not math.isfinite(resolution) or resolution <= 0.0:
            raise ValueError("resolution must be finite and greater than 0")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise TypeError("seed must be an integer")
        self._alpha: float = float(alpha)
        self._resolution: float = float(resolution)
        self._seed: int = seed

    def analyze(
        self,
        graph: object,
        relationship_types: Collection[RelationshipType] | None = None,
    ) -> GraphAnalysisResult:
        """Analyze a graph with an optional relationship-type filter."""
        if not isinstance(graph, nx.MultiDiGraph):
            raise TypeError("NetworkAnalyzer requires a NetworkX MultiDiGraph")

        filtered_graph, selected_types = self._filter_graph(graph, relationship_types)
        node_order = tuple(filtered_graph.nodes)
        node_index = {node: index for index, node in enumerate(node_order)}
        projection = self._simple_directed_projection(filtered_graph)
        undirected_projection = self._simple_undirected_projection(filtered_graph)
        weak_components = self._ordered_components(
            nx.weakly_connected_components(projection), node_index
        )
        strong_components = self._ordered_components(
            nx.strongly_connected_components(projection), node_index
        )
        weak_ids = self._component_ids(weak_components)
        strong_ids = self._component_ids(strong_components)

        node_metrics = self._node_metrics(filtered_graph, projection, node_order)
        pagerank_scores = nx.pagerank(projection, alpha=self._alpha)
        pagerank = tuple(
            PageRankScore(node_id=node, score=pagerank_scores[node])
            for node in node_order
        )
        communities = self._communities(undirected_projection, node_order)
        clustering_coefficients, average_clustering, transitivity = (
            self._clustering_metrics(undirected_projection, node_order)
        )
        community_metrics = self._community_metrics(
            undirected_projection,
            communities,
        )
        membership = tuple(
            ComponentMembership(
                node_id=node,
                weak_component_id=weak_ids[node],
                strong_component_id=strong_ids[node],
            )
            for node in node_order
        )
        statistics = GraphStatistics(
            node_count=filtered_graph.number_of_nodes(),
            edge_count=filtered_graph.number_of_edges(),
            density=nx.density(filtered_graph),
            isolated_node_count=len(list(nx.isolates(filtered_graph))),
        )
        return GraphAnalysisResult(
            statistics=statistics,
            node_metrics=node_metrics,
            weakly_connected_components=weak_components,
            strongly_connected_components=strong_components,
            component_membership=membership,
            pagerank=pagerank,
            communities=communities,
            clustering_coefficients=clustering_coefficients,
            average_clustering=average_clustering,
            transitivity=transitivity,
            community_metrics=community_metrics,
            relationship_types=selected_types,
        )

    @staticmethod
    def _filter_graph(
        graph: nx.MultiDiGraph[Any, Any],
        relationship_types: Collection[RelationshipType] | None,
    ) -> tuple[nx.MultiDiGraph[Any, Any], tuple[RelationshipType, ...] | None]:
        """Create a node-preserving filtered graph without mutating the input."""
        if relationship_types is None:
            return graph.copy(), None
        if not isinstance(relationship_types, Collection):
            raise TypeError(
                "relationship_types must be a collection of RelationshipType values"
            )

        invalid = [
            relationship_type
            for relationship_type in relationship_types
            if not isinstance(relationship_type, RelationshipType)
        ]
        if invalid:
            raise TypeError(
                "relationship_types must contain only RelationshipType values"
            )
        selected_types = tuple(
            sorted(set(relationship_types), key=lambda item: item.value)
        )
        selected = set(selected_types)
        filtered_graph: nx.MultiDiGraph[Any, Any] = nx.MultiDiGraph()
        filtered_graph.add_nodes_from(graph.nodes(data=True))
        for source, target, key, data in graph.edges(keys=True, data=True):
            if data.get("relationship_type") in selected:
                filtered_graph.add_edge(source, target, key=key, **data)
        return filtered_graph, selected_types

    @staticmethod
    def _simple_directed_projection(
        graph: nx.MultiDiGraph[Any, Any],
    ) -> nx.DiGraph[Any, Any]:
        """Collapse parallel edges while preserving directed reachability.

        Edge weights are intentionally ignored because the domain weight counts
        shared hashtags, not traversal distance or interaction cost.
        """
        projection: nx.DiGraph[Any, Any] = nx.DiGraph()
        projection.add_nodes_from(graph.nodes)
        for source, target in graph.edges():
            projection.add_edge(source, target)
        return projection

    @staticmethod
    def _simple_undirected_projection(
        graph: nx.MultiDiGraph[Any, Any],
    ) -> nx.Graph[Any]:
        """Collapse all master edges into unweighted undirected connections."""
        projection: nx.Graph[Any] = nx.Graph()
        projection.add_nodes_from(graph.nodes)
        for source, target in graph.edges():
            projection.add_edge(source, target)
        return projection

    def _communities(
        self,
        projection: nx.Graph[Any],
        node_order: tuple[str, ...],
    ) -> CommunityDetectionResult:
        """Run Louvain and assign stable IDs independent of set iteration."""
        raw_communities = nx.community.louvain_communities(
            projection,
            weight=None,
            resolution=self._resolution,
            seed=self._seed,
        )
        node_index = {node: index for index, node in enumerate(node_order)}
        ordered_members = sorted(
            (
                tuple(sorted(community, key=node_index.__getitem__))
                for community in raw_communities
            ),
            key=lambda members: node_index[members[0]],
        )
        communities = tuple(
            Community(
                community_id=community_id,
                members=members,
                size=len(members),
            )
            for community_id, members in enumerate(ordered_members)
        )
        memberships = tuple(
            CommunityMembership(node_id=node, community_id=community_id)
            for community_id, community in enumerate(communities)
            for node in community.members
        )
        memberships = tuple(
            sorted(memberships, key=lambda item: node_index[item.node_id])
        )
        return CommunityDetectionResult(
            communities=communities,
            memberships=memberships,
            community_count=len(communities),
        )

    @staticmethod
    def _clustering_metrics(
        projection: nx.Graph[Any],
        node_order: tuple[str, ...],
    ) -> tuple[tuple[ClusteringCoefficient, ...], float, float]:
        coefficients = cast(dict[Any, float], nx.clustering(projection))
        clustering_coefficients = tuple(
            ClusteringCoefficient(node_id=node, coefficient=coefficients[node])
            for node in node_order
        )
        average_clustering = (
            nx.average_clustering(projection) if projection.number_of_nodes() else 0.0
        )
        transitivity = (
            nx.transitivity(projection) if projection.number_of_nodes() else 0.0
        )
        return clustering_coefficients, average_clustering, transitivity

    @staticmethod
    def _community_metrics(
        projection: nx.Graph[Any],
        communities: CommunityDetectionResult,
    ) -> tuple[CommunityStructuralMetrics, ...]:
        results = []
        for community in communities.communities:
            subgraph = projection.subgraph(community.members)
            node_count = len(community.members)
            internal_coefficients = cast(dict[Any, float], nx.clustering(subgraph))
            results.append(
                CommunityStructuralMetrics(
                    community_id=community.community_id,
                    node_count=node_count,
                    internal_edge_count=subgraph.number_of_edges(),
                    internal_density=(nx.density(subgraph) if node_count > 1 else 0.0),
                    average_clustering=(
                        sum(internal_coefficients.values()) / node_count
                        if node_count
                        else 0.0
                    ),
                )
            )
        return tuple(results)

    @staticmethod
    def _ordered_components(
        components: Any,
        node_index: dict[Any, int],
    ) -> tuple[tuple[str, ...], ...]:
        ordered = (
            tuple(sorted(component, key=node_index.__getitem__))
            for component in components
        )
        return tuple(sorted(ordered, key=lambda component: node_index[component[0]]))

    @staticmethod
    def _component_ids(
        components: tuple[tuple[str, ...], ...],
    ) -> dict[str, int]:
        return {
            node: component_id
            for component_id, component in enumerate(components)
            for node in component
        }

    @classmethod
    def _node_metrics(
        cls,
        graph: nx.MultiDiGraph[Any, Any],
        projection: nx.DiGraph[Any, Any],
        node_order: tuple[str, ...],
    ) -> tuple[NodeMetrics, ...]:
        node_count = graph.number_of_nodes()
        denominator = max(node_count - 1, 1)
        degree_centrality = nx.degree_centrality(graph)
        if node_count == 1:
            degree_centrality = dict.fromkeys(node_order, 0.0)
        betweenness = nx.betweenness_centrality(projection, normalized=True)
        closeness = nx.closeness_centrality(projection)
        return tuple(
            NodeMetrics(
                node_id=node,
                degree=graph.degree(node),
                in_degree=graph.in_degree(node),
                out_degree=graph.out_degree(node),
                degree_centrality=degree_centrality[node],
                in_degree_centrality=graph.in_degree(node) / denominator
                if node_count > 1
                else 0.0,
                out_degree_centrality=graph.out_degree(node) / denominator
                if node_count > 1
                else 0.0,
                betweenness_centrality=betweenness[node],
                closeness_centrality=closeness[node],
            )
            for node in node_order
        )
