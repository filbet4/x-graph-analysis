"""Tests for fixed-window temporal graph analysis.

TODO: Add tests for larger timestamped fixtures when temporal methodology is finalized.
"""

from datetime import UTC, datetime, timedelta

import networkx as nx
import pytest

from x_graph_analysis.analysis.temporal import (
    TemporalAnalysisError,
    TemporalNetworkAnalyzer,
)
from x_graph_analysis.domain.models import RelationshipType

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def make_graph(
    timestamps: dict[str, datetime],
    edges: tuple[tuple[str, str, RelationshipType], ...] = (),
) -> nx.MultiDiGraph:
    """Create a timestamped multigraph with domain-style edge attributes."""
    graph = nx.MultiDiGraph()
    for node, timestamp in timestamps.items():
        graph.add_node(node, created_at=timestamp, label=f"{node}-metadata")
    for source, target, relationship_type in edges:
        graph.add_edge(
            source,
            target,
            relationship_type=relationship_type,
            weight=1,
            directed=relationship_type is not RelationshipType.SHARED_HASHTAG,
        )
    return graph


def test_empty_graph_without_range_has_no_windows() -> None:
    """An empty graph without boundaries has no meaningful temporal range."""
    result = TemporalNetworkAnalyzer().analyze(nx.MultiDiGraph(), timedelta(days=1))

    assert result.start is None
    assert result.end is None
    assert result.windows == ()


def test_empty_graph_with_explicit_range_includes_empty_windows() -> None:
    """An explicit range retains structurally consistent empty windows."""
    result = TemporalNetworkAnalyzer().analyze(
        nx.MultiDiGraph(),
        timedelta(days=1),
        start=BASE,
        end=BASE + timedelta(days=3),
    )

    assert len(result.windows) == 3
    assert all(window.analysis.statistics.node_count == 0 for window in result.windows)
    assert result.windows[0].start == BASE
    assert result.windows[-1].end == BASE + timedelta(days=3)


def test_single_timestamp_creates_one_window() -> None:
    """One post is placed in one full fixed-duration window."""
    result = TemporalNetworkAnalyzer().analyze(
        make_graph({"a": BASE}), timedelta(days=1)
    )

    assert len(result.windows) == 1
    assert result.windows[0].start == BASE
    assert result.windows[0].end == BASE + timedelta(days=1)
    assert result.windows[0].analysis.statistics.node_count == 1


def test_windows_are_half_open_at_exact_boundaries() -> None:
    """A timestamp at an end boundary belongs to the next window."""
    result = TemporalNetworkAnalyzer().analyze(
        make_graph(
            {
                "first": BASE,
                "second": BASE + timedelta(days=1),
            }
        ),
        timedelta(days=1),
    )

    assert [window.analysis.statistics.node_count for window in result.windows] == [
        1,
        1,
    ]
    assert result.windows[0].analysis.node_metrics[0].node_id == "first"
    assert result.windows[1].analysis.node_metrics[0].node_id == "second"


def test_empty_intermediate_window_is_included() -> None:
    """A gap between posts produces an empty middle window."""
    result = TemporalNetworkAnalyzer().analyze(
        make_graph(
            {
                "first": BASE,
                "last": BASE + timedelta(days=2, hours=1),
            }
        ),
        timedelta(days=1),
    )

    assert len(result.windows) == 3
    assert [window.analysis.statistics.node_count for window in result.windows] == [
        1,
        0,
        1,
    ]


def test_final_partial_window_uses_explicit_end() -> None:
    """An explicit range may end part-way through the final fixed window."""
    result = TemporalNetworkAnalyzer().analyze(
        make_graph({"a": BASE, "b": BASE + timedelta(days=1, hours=6)}),
        timedelta(days=1),
        start=BASE,
        end=BASE + timedelta(days=1, hours=12),
    )

    assert len(result.windows) == 2
    assert result.windows[-1].start == BASE + timedelta(days=1)
    assert result.windows[-1].end == BASE + timedelta(days=1, hours=12)
    assert result.windows[-1].analysis.statistics.node_count == 1


def test_cross_window_edges_are_excluded_and_intra_window_edges_preserved() -> None:
    """Each window is an induced subgraph of posts inside that window."""
    graph = make_graph(
        {"a": BASE, "b": BASE, "c": BASE + timedelta(days=1)},
        (
            ("a", "b", RelationshipType.REPLY),
            ("b", "c", RelationshipType.QUOTE),
        ),
    )

    result = TemporalNetworkAnalyzer().analyze(graph, timedelta(days=1))

    assert result.windows[0].analysis.statistics.node_count == 2
    assert result.windows[0].analysis.statistics.edge_count == 1
    assert result.windows[1].analysis.statistics.node_count == 1
    assert result.windows[1].analysis.statistics.edge_count == 0


def test_parallel_edges_and_attributes_are_preserved_in_window() -> None:
    """Induced subgraphs retain multiedge multiplicity and edge metadata."""
    graph = make_graph(
        {"a": BASE, "b": BASE},
        (
            ("a", "b", RelationshipType.REPLY),
            ("a", "b", RelationshipType.QUOTE),
        ),
    )

    result = TemporalNetworkAnalyzer().analyze(graph, timedelta(days=1))
    analysis = result.windows[0].analysis

    assert analysis.statistics.edge_count == 2
    assert analysis.node_metrics[0].node_id == "a"
    assert graph.number_of_edges() == 2


def test_relationship_filter_is_forwarded_to_each_window() -> None:
    """Temporal analysis delegates relationship filtering to NetworkAnalyzer."""
    graph = make_graph(
        {"a": BASE, "b": BASE, "c": BASE + timedelta(days=1)},
        (
            ("a", "b", RelationshipType.REPLY),
            ("a", "b", RelationshipType.QUOTE),
            ("b", "c", RelationshipType.REPOST),
        ),
    )

    result = TemporalNetworkAnalyzer().analyze(
        graph,
        timedelta(days=1),
        relationship_types={RelationshipType.REPLY},
    )

    assert result.windows[0].analysis.relationship_types == (RelationshipType.REPLY,)
    assert result.windows[0].analysis.statistics.edge_count == 1
    assert result.windows[1].analysis.relationship_types == (RelationshipType.REPLY,)
    assert result.windows[1].analysis.statistics.edge_count == 0


def test_explicit_range_and_windows_are_chronological_and_deterministic() -> None:
    """Repeated partitioning returns equal chronologically ordered results."""
    graph = make_graph({"a": BASE, "b": BASE + timedelta(days=1)}, ())
    analyzer = TemporalNetworkAnalyzer()
    first = analyzer.analyze(
        graph,
        timedelta(days=1),
        start=BASE,
        end=BASE + timedelta(days=2),
    )
    second = analyzer.analyze(
        graph,
        timedelta(days=1),
        start=BASE,
        end=BASE + timedelta(days=2),
    )

    assert first == second
    assert [window.start for window in first.windows] == [
        BASE,
        BASE + timedelta(days=1),
    ]


def test_temporal_analysis_does_not_mutate_master_graph() -> None:
    """Partitioning and delegated analysis leave the master graph unchanged."""
    graph = make_graph(
        {"a": BASE, "b": BASE},
        (("a", "b", RelationshipType.REPLY),),
    )
    before_nodes = list(graph.nodes(data=True))
    before_edges = list(graph.edges(keys=True, data=True))

    TemporalNetworkAnalyzer().analyze(graph, timedelta(days=1))

    assert list(graph.nodes(data=True)) == before_nodes
    assert list(graph.edges(keys=True, data=True)) == before_edges


@pytest.mark.parametrize(
    "window_size",
    (timedelta(0), timedelta(days=-1), "1 day"),
)
def test_invalid_window_sizes_are_rejected(window_size: object) -> None:
    """Window size must be a positive timedelta."""
    with pytest.raises((TemporalAnalysisError, TypeError)):
        TemporalNetworkAnalyzer().analyze(
            make_graph({"a": BASE}),
            window_size,  # type: ignore[arg-type]
        )


def test_naive_node_timestamp_is_rejected() -> None:
    """Naive timestamps cannot be assigned safely to timezone-aware windows."""
    with pytest.raises(TemporalAnalysisError, match="timezone-aware"):
        TemporalNetworkAnalyzer().analyze(
            make_graph({"a": datetime(2026, 1, 1)}), timedelta(days=1)
        )


def test_invalid_explicit_range_is_rejected() -> None:
    """Explicit ranges require aware timestamps and start before end."""
    with pytest.raises(TemporalAnalysisError, match="start must be before end"):
        TemporalNetworkAnalyzer().analyze(
            make_graph({"a": BASE}),
            timedelta(days=1),
            start=BASE + timedelta(days=1),
            end=BASE,
        )

    with pytest.raises(TemporalAnalysisError, match="timezone-aware"):
        TemporalNetworkAnalyzer().analyze(
            make_graph({"a": BASE}),
            timedelta(days=1),
            start=datetime(2026, 1, 1),
            end=BASE + timedelta(days=1),
        )
