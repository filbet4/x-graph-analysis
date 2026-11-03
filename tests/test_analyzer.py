"""Tests for structural analysis of NetworkX multigraphs.

TODO: Add benchmark fixtures when realistic thesis-sized graphs are available.
"""

from datetime import UTC, datetime

import networkx as nx
import pytest

from x_graph_analysis.analysis.analyzer import NetworkAnalyzer
from x_graph_analysis.domain.models import (
    Post,
    PostCollection,
    Relationship,
    RelationshipType,
    User,
)
from x_graph_analysis.graph.builder import NetworkXGraphBuilder

COLLECTED_AT = datetime(2026, 8, 1, 12, tzinfo=UTC)
PUBLISHED_AT = datetime(2026, 8, 1, 9, tzinfo=UTC)


def make_post(post_id: str) -> Post:
    """Create a minimal post node for analyzer tests."""
    return Post(
        post_id=post_id,
        author=User(user_id=f"user-{post_id}", username=f"user_{post_id}"),
        text=f"Post {post_id}",
        published_at=PUBLISHED_AT,
    )


def make_graph(
    post_ids: tuple[str, ...],
    relationships: tuple[Relationship, ...] = (),
) -> nx.MultiDiGraph:
    """Build a master graph from explicit domain relationships."""
    collection = PostCollection(
        posts=tuple(make_post(post_id) for post_id in post_ids),
        source_name="test",
        collected_at=COLLECTED_AT,
    )
    return NetworkXGraphBuilder().build(collection, relationships)


def metrics_by_node(result: object) -> dict[str, object]:
    """Return node metrics keyed by node ID for readable assertions."""
    return {metric.node_id: metric for metric in result.node_metrics}  # type: ignore[attr-defined]


def pagerank_by_node(result: object) -> dict[str, float]:
    """Return PageRank scores keyed by node ID for readable assertions."""
    return {
        score.node_id: score.score
        for score in result.pagerank  # type: ignore[attr-defined]
    }


def community_members_by_id(result: object) -> tuple[tuple[str, ...], ...]:
    """Return ordered community members without relying on raw Louvain IDs."""
    return tuple(
        community.members
        for community in result.communities.communities  # type: ignore[attr-defined]
    )


def clustering_by_node(result: object) -> dict[str, float]:
    """Return local clustering coefficients keyed by node ID."""
    return {
        metric.node_id: metric.coefficient
        for metric in result.clustering_coefficients  # type: ignore[attr-defined]
    }


def test_empty_graph_has_zero_statistics_and_no_components() -> None:
    """An empty graph produces a valid empty analysis result."""
    result = NetworkAnalyzer().analyze(nx.MultiDiGraph())

    assert result.statistics.node_count == 0
    assert result.statistics.edge_count == 0
    assert result.statistics.density == 0.0
    assert result.statistics.isolated_node_count == 0
    assert result.node_metrics == ()
    assert result.weakly_connected_components == ()
    assert result.strongly_connected_components == ()
    assert result.component_membership == ()
    assert result.pagerank == ()
    assert result.clustering_coefficients == ()
    assert result.average_clustering == 0.0
    assert result.transitivity == 0.0
    assert result.community_metrics == ()


def test_single_node_is_isolated_with_zero_centralities() -> None:
    """A singleton has zero degree and path-based centrality values."""
    graph = make_graph(("only",))

    result = NetworkAnalyzer().analyze(graph)
    metric = result.node_metrics[0]

    assert result.statistics.isolated_node_count == 1
    assert metric.node_id == "only"
    assert metric.degree == 0
    assert metric.in_degree == 0
    assert metric.out_degree == 0
    assert metric.degree_centrality == 0.0
    assert metric.in_degree_centrality == 0.0
    assert metric.out_degree_centrality == 0.0
    assert metric.betweenness_centrality == 0.0
    assert metric.closeness_centrality == 0.0
    assert pagerank_by_node(result)["only"] == pytest.approx(1.0)
    assert clustering_by_node(result)["only"] == 0.0
    assert result.average_clustering == 0.0
    assert result.transitivity == 0.0
    assert result.community_metrics[0].internal_edge_count == 0
    assert result.community_metrics[0].internal_density == 0.0
    assert result.community_metrics[0].average_clustering == 0.0


def test_triangle_has_full_local_and_graph_clustering() -> None:
    """Every triangle node has coefficient one and transitivity one."""
    relationships = tuple(
        Relationship(source, target, RelationshipType.REPLY)
        for source, target in (
            ("a", "b"),
            ("b", "a"),
            ("b", "c"),
            ("c", "b"),
            ("a", "c"),
            ("c", "a"),
        )
    )

    result = NetworkAnalyzer().analyze(make_graph(("a", "b", "c"), relationships))

    assert clustering_by_node(result) == pytest.approx({"a": 1.0, "b": 1.0, "c": 1.0})
    assert result.average_clustering == pytest.approx(1.0)
    assert result.transitivity == pytest.approx(1.0)


def test_path_has_zero_local_clustering_and_transitivity() -> None:
    """A simple three-node path contains no closed triplets."""
    result = NetworkAnalyzer().analyze(
        make_graph(
            ("a", "b", "c"),
            (
                Relationship("a", "b", RelationshipType.REPLY),
                Relationship("b", "c", RelationshipType.REPLY),
            ),
        )
    )

    assert clustering_by_node(result) == pytest.approx({"a": 0.0, "b": 0.0, "c": 0.0})
    assert result.average_clustering == pytest.approx(0.0)
    assert result.transitivity == pytest.approx(0.0)


def test_two_node_graph_and_no_edge_graph_have_zero_clustering() -> None:
    """Graphs without valid degree-two triplets return zero graph metrics."""
    two_node = NetworkAnalyzer().analyze(
        make_graph(("a", "b"), (Relationship("a", "b", RelationshipType.REPLY),))
    )
    no_edge = NetworkAnalyzer().analyze(make_graph(("a", "b")))

    for result in (two_node, no_edge):
        assert result.average_clustering == 0.0
        assert result.transitivity == 0.0
        assert all(value == 0.0 for value in clustering_by_node(result).values())


def test_community_metrics_report_internal_edges_density_and_average_clustering() -> (
    None
):
    """A detected triangle community reports three internal edges and density one."""
    group = ("a", "b", "c")
    relationships = tuple(
        Relationship(source, target, RelationshipType.REPLY)
        for source in group
        for target in group
        if source != target
    )

    result = NetworkAnalyzer().analyze(make_graph(group, relationships))

    assert len(result.community_metrics) == 1
    community = result.community_metrics[0]
    assert community.node_count == 3
    assert community.internal_edge_count == 3
    assert community.internal_density == pytest.approx(1.0)
    assert community.average_clustering == pytest.approx(1.0)


def test_community_clustering_is_computed_inside_community() -> None:
    """External neighbors must not lower a community's internal clustering."""
    group_a = ("a", "b", "c")
    group_b = ("d", "e", "f")
    relationships = tuple(
        Relationship(source, target, RelationshipType.REPLY)
        for group in (group_a, group_b)
        for source in group
        for target in group
        if source != target
    ) + (Relationship("a", "d", RelationshipType.REPLY),)

    result = NetworkAnalyzer(seed=42).analyze(
        make_graph(group_a + group_b, relationships)
    )
    community_a = next(
        metrics
        for metrics in result.community_metrics
        if "a" in result.communities.communities[metrics.community_id].members
    )
    global_a = clustering_by_node(result)["a"]

    assert global_a < 1.0
    assert community_a.average_clustering == pytest.approx(1.0)


def test_parallel_and_opposite_edges_do_not_change_undirected_clustering() -> None:
    """Equivalent simple undirected projections produce equal cohesion metrics."""
    collapsed = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "c", RelationshipType.REPLY),
            Relationship("a", "c", RelationshipType.REPLY),
        ),
    )
    redundant = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("a", "b", RelationshipType.QUOTE),
            Relationship("b", "a", RelationshipType.REPOST),
            Relationship("b", "c", RelationshipType.REPLY),
            Relationship("c", "b", RelationshipType.QUOTE),
            Relationship("a", "c", RelationshipType.REPLY),
            Relationship("c", "a", RelationshipType.REPOST),
        ),
    )

    first = NetworkAnalyzer().analyze(collapsed)
    second = NetworkAnalyzer().analyze(redundant)

    assert clustering_by_node(first) == pytest.approx(clustering_by_node(second))
    assert first.average_clustering == pytest.approx(second.average_clustering)
    assert first.transitivity == pytest.approx(second.transitivity)
    assert first.community_metrics == second.community_metrics


def test_directed_chain_has_expected_degrees_components_and_centrality() -> None:
    """A -> B -> C exposes degree, connectivity, and path metrics."""
    graph = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )

    result = NetworkAnalyzer().analyze(graph)
    metrics = metrics_by_node(result)

    assert result.statistics.node_count == 3
    assert result.statistics.edge_count == 2
    assert result.statistics.density == pytest.approx(1 / 3)
    assert result.statistics.isolated_node_count == 0
    assert result.weakly_connected_components == (("a", "b", "c"),)
    assert result.strongly_connected_components == (("a",), ("b",), ("c",))
    assert metrics["a"].degree == 1
    assert metrics["a"].in_degree == 0
    assert metrics["a"].out_degree == 1
    assert metrics["b"].degree == 2
    assert metrics["b"].in_degree == 1
    assert metrics["b"].out_degree == 1
    assert metrics["c"].in_degree == 1
    assert metrics["c"].out_degree == 0
    assert metrics["b"].degree_centrality == pytest.approx(1.0)
    assert metrics["b"].betweenness_centrality == pytest.approx(0.5)
    assert metrics["a"].closeness_centrality == pytest.approx(0.0)
    assert metrics["b"].closeness_centrality == pytest.approx(0.5)
    assert metrics["c"].closeness_centrality == pytest.approx(2 / 3)
    pagerank = pagerank_by_node(result)
    assert sum(pagerank.values()) == pytest.approx(1.0)
    assert pagerank["c"] > pagerank["b"] > pagerank["a"]


def test_directed_cycle_has_equal_pagerank_scores() -> None:
    """A symmetric directed cycle distributes PageRank equally."""
    graph = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "c", RelationshipType.REPLY),
            Relationship("c", "a", RelationshipType.REPLY),
        ),
    )

    pagerank = pagerank_by_node(NetworkAnalyzer().analyze(graph))

    assert sum(pagerank.values()) == pytest.approx(1.0)
    assert pagerank["a"] == pytest.approx(1 / 3)
    assert pagerank["a"] == pytest.approx(pagerank["b"])
    assert pagerank["b"] == pytest.approx(pagerank["c"])


def test_disconnected_graph_and_isolated_node_receive_pagerank() -> None:
    """PageRank includes every node, including isolated nodes."""
    graph = make_graph(
        ("a", "b", "isolated"),
        (Relationship("a", "b", RelationshipType.REPLY),),
    )

    pagerank = pagerank_by_node(NetworkAnalyzer().analyze(graph))

    assert set(pagerank) == {"a", "b", "isolated"}
    assert sum(pagerank.values()) == pytest.approx(1.0)
    assert all(score > 0.0 for score in pagerank.values())


def test_parallel_edges_are_collapsed_for_pagerank() -> None:
    """Parallel relationship types do not increase PageRank arc weight."""
    parallel_graph = make_graph(
        ("a", "b"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("a", "b", RelationshipType.QUOTE),
        ),
    )
    simple_graph = make_graph(
        ("a", "b"),
        (Relationship("a", "b", RelationshipType.REPLY),),
    )

    parallel_scores = pagerank_by_node(NetworkAnalyzer().analyze(parallel_graph))
    simple_scores = pagerank_by_node(NetworkAnalyzer().analyze(simple_graph))

    assert parallel_scores == pytest.approx(simple_scores)


def test_alpha_is_configurable() -> None:
    """Changing alpha changes scores while retaining normalization."""
    graph = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )

    default_scores = pagerank_by_node(NetworkAnalyzer().analyze(graph))
    custom_scores = pagerank_by_node(NetworkAnalyzer(alpha=0.5).analyze(graph))

    assert sum(custom_scores.values()) == pytest.approx(1.0)
    assert custom_scores != pytest.approx(default_scores)


@pytest.mark.parametrize("alpha", (0.0, -0.1, 1.1, float("nan"), float("inf")))
def test_invalid_alpha_values_are_rejected(alpha: float) -> None:
    """PageRank alpha must be finite and strictly between zero and one."""
    with pytest.raises(ValueError, match="0 < alpha <= 1"):
        NetworkAnalyzer(alpha=alpha)


def test_non_numeric_alpha_is_rejected() -> None:
    """Non-numeric damping factors fail before analysis begins."""
    with pytest.raises(TypeError, match="real number"):
        NetworkAnalyzer(alpha="0.85")  # type: ignore[arg-type]


def test_empty_graph_has_no_communities() -> None:
    """An empty graph produces an empty community result."""
    result = NetworkAnalyzer().analyze(nx.MultiDiGraph())

    assert result.communities.community_count == 0
    assert result.communities.communities == ()
    assert result.communities.memberships == ()


def test_single_and_isolated_nodes_are_singleton_communities() -> None:
    """Nodes without edges are retained as independent communities."""
    result = NetworkAnalyzer().analyze(make_graph(("a", "b", "c")))

    assert result.communities.community_count == 3
    assert community_members_by_id(result) == (("a",), ("b",), ("c",))
    assert tuple(
        membership.community_id for membership in result.communities.memberships
    ) == (0, 1, 2)


def test_disconnected_components_remain_separate_communities() -> None:
    """Disconnected graph components cannot be joined by Louvain edges."""
    relationships = (
        Relationship("a", "b", RelationshipType.REPLY),
        Relationship("b", "a", RelationshipType.REPLY),
        Relationship("c", "d", RelationshipType.REPLY),
        Relationship("d", "c", RelationshipType.REPLY),
    )

    result = NetworkAnalyzer().analyze(make_graph(("a", "b", "c", "d"), relationships))

    assert community_members_by_id(result) == (("a", "b"), ("c", "d"))
    assert tuple(community.size for community in result.communities.communities) == (
        2,
        2,
    )


def test_two_clearly_separated_groups_are_detected() -> None:
    """Two dense groups connected internally are assigned separately."""
    group_a = ("a1", "a2", "a3")
    group_b = ("b1", "b2", "b3")
    relationships = tuple(
        Relationship(source, target, RelationshipType.REPLY)
        for group in (group_a, group_b)
        for source in group
        for target in group
        if source != target
    )

    result = NetworkAnalyzer(seed=42).analyze(
        make_graph(group_a + group_b, relationships)
    )

    assert {frozenset(members) for members in community_members_by_id(result)} == {
        frozenset(group_a),
        frozenset(group_b),
    }


def test_parallel_edges_collapse_for_community_projection() -> None:
    """Parallel edge types do not create stronger community connections."""
    parallel = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("a", "b", RelationshipType.QUOTE),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )
    simple = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )

    assert community_members_by_id(NetworkAnalyzer().analyze(parallel)) == (
        community_members_by_id(NetworkAnalyzer().analyze(simple))
    )


def test_opposite_directed_edges_collapse_for_community_projection() -> None:
    """Opposite arcs represent one undirected connection for Louvain."""
    opposite = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "a", RelationshipType.QUOTE),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )
    undirected_equivalent = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )

    assert community_members_by_id(NetworkAnalyzer().analyze(opposite)) == (
        community_members_by_id(NetworkAnalyzer().analyze(undirected_equivalent))
    )


def test_community_detection_is_reproducible_and_ids_are_deterministic() -> None:
    """Fixed seed and graph insertion order yield identical community results."""
    graph = make_graph(
        ("a", "b", "c", "d"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "a", RelationshipType.REPLY),
            Relationship("c", "d", RelationshipType.REPLY),
            Relationship("d", "c", RelationshipType.REPLY),
        ),
    )

    first = NetworkAnalyzer(seed=7).analyze(graph).communities
    second = NetworkAnalyzer(seed=7).analyze(graph).communities

    assert first == second
    assert tuple(item.community_id for item in first.communities) == (0, 1)
    assert tuple(item.node_id for item in first.memberships) == ("a", "b", "c", "d")


def test_resolution_is_configurable() -> None:
    """A positive resolution value is accepted and produces typed results."""
    result = NetworkAnalyzer(resolution=0.5).analyze(make_graph(("a", "b")))

    assert result.communities.community_count == 2


@pytest.mark.parametrize("resolution", (0.0, -1.0, float("nan"), float("inf")))
def test_invalid_resolution_values_are_rejected(resolution: float) -> None:
    """Louvain resolution must be finite and strictly positive."""
    with pytest.raises(ValueError, match="greater than 0"):
        NetworkAnalyzer(resolution=resolution)


def test_non_numeric_resolution_is_rejected() -> None:
    """Non-numeric resolution values fail before analysis begins."""
    with pytest.raises(TypeError, match="real number"):
        NetworkAnalyzer(resolution="1.0")  # type: ignore[arg-type]


def make_filter_graph() -> nx.MultiDiGraph:
    """Create a graph containing several relationship types and isolated nodes."""
    return make_graph(
        ("a", "b", "c", "d"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("a", "b", RelationshipType.QUOTE),
            Relationship("b", "c", RelationshipType.REPOST),
            Relationship(
                "c",
                "d",
                RelationshipType.SHARED_HASHTAG,
                directed=False,
            ),
        ),
    )


def test_unfiltered_analysis_preserves_current_behavior_and_metadata() -> None:
    """Omitting the filter analyzes every master edge and records no filter."""
    graph = make_filter_graph()

    result = NetworkAnalyzer().analyze(graph)

    assert result.relationship_types is None
    assert result.statistics.edge_count == 5
    assert result.node_metrics[0].out_degree == 2


def test_filter_selects_only_requested_edges_and_preserves_all_nodes() -> None:
    """Filtering affects topology and metrics while retaining every node."""
    graph = make_filter_graph()

    result = NetworkAnalyzer().analyze(
        graph,
        relationship_types={RelationshipType.REPLY},
    )

    assert result.relationship_types == (RelationshipType.REPLY,)
    assert result.statistics.node_count == 4
    assert result.statistics.edge_count == 1
    assert result.statistics.isolated_node_count == 2
    assert result.weakly_connected_components == (("a", "b"), ("c",), ("d",))
    assert metrics_by_node(result)["a"].out_degree == 1
    assert metrics_by_node(result)["b"].in_degree == 1
    assert metrics_by_node(result)["c"].degree == 0
    assert set(pagerank_by_node(result)) == {"a", "b", "c", "d"}
    assert result.communities.community_count == 3
    assert result.average_clustering == 0.0


def test_multiple_selected_types_preserve_parallel_edges() -> None:
    """Selecting reply and quote keeps both master edges between a and b."""
    graph = make_filter_graph()

    result = NetworkAnalyzer().analyze(
        graph,
        relationship_types={RelationshipType.QUOTE, RelationshipType.REPLY},
    )

    assert result.relationship_types == (
        RelationshipType.QUOTE,
        RelationshipType.REPLY,
    )
    assert result.statistics.edge_count == 2
    assert metrics_by_node(result)["a"].out_degree == 2
    assert metrics_by_node(result)["b"].in_degree == 2
    assert result.weakly_connected_components == (("a", "b"), ("c",), ("d",))


def test_filter_with_no_matching_edges_creates_edgeless_analysis() -> None:
    """A valid type with no edges leaves all nodes isolated."""
    result = NetworkAnalyzer().analyze(
        make_filter_graph(),
        relationship_types={RelationshipType.MENTION},
    )

    assert result.relationship_types == (RelationshipType.MENTION,)
    assert result.statistics.edge_count == 0
    assert result.statistics.isolated_node_count == 4
    assert result.weakly_connected_components == (("a",), ("b",), ("c",), ("d",))
    assert result.average_clustering == 0.0
    assert result.transitivity == 0.0
    assert result.communities.community_count == 4


def test_explicit_all_types_matches_unfiltered_analysis() -> None:
    """Selecting every enum value produces the same analysis as no filter."""
    graph = make_filter_graph()
    all_types = set(RelationshipType)

    unfiltered = NetworkAnalyzer().analyze(graph)
    explicitly_all = NetworkAnalyzer().analyze(graph, relationship_types=all_types)

    assert explicitly_all.relationship_types == tuple(
        sorted(all_types, key=lambda item: item.value)
    )
    assert explicitly_all.statistics == unfiltered.statistics
    assert explicitly_all.node_metrics == unfiltered.node_metrics
    assert explicitly_all.pagerank == pytest.approx(unfiltered.pagerank)
    assert explicitly_all.communities == unfiltered.communities
    assert explicitly_all.clustering_coefficients == unfiltered.clustering_coefficients
    assert explicitly_all.community_metrics == unfiltered.community_metrics


def test_empty_explicit_filter_preserves_nodes_and_selects_no_edges() -> None:
    """An explicit empty set differs from the omitted filter and is edgeless."""
    result = NetworkAnalyzer().analyze(make_filter_graph(), relationship_types=set())

    assert result.relationship_types == ()
    assert result.statistics.node_count == 4
    assert result.statistics.edge_count == 0
    assert result.statistics.isolated_node_count == 4


@pytest.mark.parametrize(
    "relationship_types",
    (("reply",), (RelationshipType.REPLY, "quote")),
)
def test_invalid_relationship_type_filters_are_rejected(
    relationship_types: tuple[object, ...],
) -> None:
    """Raw strings and mixed values are not accepted as relationship filters."""
    with pytest.raises(TypeError, match="only RelationshipType"):
        NetworkAnalyzer().analyze(
            make_filter_graph(),
            relationship_types=relationship_types,  # type: ignore[arg-type]
        )


def test_filtering_does_not_mutate_master_graph_and_is_deterministic() -> None:
    """Repeated filtered analyses match and preserve master nodes and edges."""
    graph = make_filter_graph()
    before_nodes = list(graph.nodes(data=True))
    before_edges = list(graph.edges(keys=True, data=True))
    analyzer = NetworkAnalyzer()

    first = analyzer.analyze(graph, relationship_types={RelationshipType.REPLY})
    second = analyzer.analyze(graph, relationship_types={RelationshipType.REPLY})

    assert first == second
    assert list(graph.nodes(data=True)) == before_nodes
    assert list(graph.edges(keys=True, data=True)) == before_edges


def test_disconnected_and_strongly_connected_components_are_reported() -> None:
    """Weak and strong components differ for directed pairs and isolates."""
    graph = make_graph(
        ("a", "b", "c", "d", "e"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("b", "a", RelationshipType.REPLY),
            Relationship("c", "d", RelationshipType.REPLY),
        ),
    )

    result = NetworkAnalyzer().analyze(graph)

    assert result.weakly_connected_components == (("a", "b"), ("c", "d"), ("e",))
    assert result.strongly_connected_components == (
        ("a", "b"),
        ("c",),
        ("d",),
        ("e",),
    )
    assert result.component_membership == (
        result.component_membership[0],
        result.component_membership[1],
        result.component_membership[2],
        result.component_membership[3],
        result.component_membership[4],
    )
    membership = {
        item.node_id: (item.weak_component_id, item.strong_component_id)
        for item in result.component_membership
    }
    assert membership == {
        "a": (0, 0),
        "b": (0, 0),
        "c": (1, 1),
        "d": (1, 2),
        "e": (2, 3),
    }


def test_multiedge_degree_counts_and_projection_collapses_parallel_edges() -> None:
    """Parallel master edges count for degree but one projection arc for paths."""
    graph = make_graph(
        ("a", "b", "c"),
        (
            Relationship("a", "b", RelationshipType.REPLY),
            Relationship("a", "b", RelationshipType.QUOTE),
            Relationship(
                "a",
                "b",
                RelationshipType.SHARED_HASHTAG,
                weight=2,
                directed=False,
            ),
            Relationship("b", "c", RelationshipType.REPLY),
        ),
    )

    result = NetworkAnalyzer().analyze(graph)
    metrics = metrics_by_node(result)

    assert result.statistics.edge_count == 5
    assert metrics["a"].out_degree == 3
    assert metrics["b"].in_degree == 3
    assert metrics["b"].out_degree == 2
    assert metrics["b"].betweenness_centrality == pytest.approx(0.5)


def test_analysis_is_deterministic_and_does_not_mutate_master_graph() -> None:
    """Repeated analysis is equal and leaves nodes, edges, and attributes unchanged."""
    graph = make_graph(
        ("a", "b", "c"),
        (Relationship("a", "b", RelationshipType.REPLY),),
    )
    before_nodes = list(graph.nodes(data=True))
    before_edges = list(graph.edges(keys=True, data=True))

    analyzer = NetworkAnalyzer()
    first = analyzer.analyze(graph)
    second = analyzer.analyze(graph)

    assert first == second
    assert first.pagerank == second.pagerank
    assert list(graph.nodes(data=True)) == before_nodes
    assert list(graph.edges(keys=True, data=True)) == before_edges


def test_analyzer_requires_a_multidigraph() -> None:
    """The analyzer rejects graph types whose semantics are not its contract."""
    with pytest.raises(TypeError, match="MultiDiGraph"):
        NetworkAnalyzer().analyze(nx.DiGraph())
