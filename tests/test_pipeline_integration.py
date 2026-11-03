"""End-to-end integration tests for the current local analysis pipeline.

TODO: Add an external-source integration test after X API access is implemented.
"""

from copy import deepcopy
from datetime import timedelta
from pathlib import Path

from x_graph_analysis.adapters.sources.json_file import LocalJsonPostSource
from x_graph_analysis.analysis.analyzer import GraphAnalysisResult, NetworkAnalyzer
from x_graph_analysis.analysis.temporal import TemporalNetworkAnalyzer
from x_graph_analysis.domain.models import RelationshipType
from x_graph_analysis.graph.builder import NetworkXGraphBuilder, RelationshipBuilder

SAMPLE_FILE = Path(__file__).parents[1] / "data" / "sample_posts.json"


def test_sample_data_runs_through_complete_analysis_pipeline() -> None:
    """The real local source can feed detection, construction, and analysis."""
    collection = LocalJsonPostSource(SAMPLE_FILE).collect()
    original_collection = deepcopy(collection)

    relationships = RelationshipBuilder().build(collection)
    graph = NetworkXGraphBuilder().build(collection, relationships)
    analysis = NetworkAnalyzer().analyze(graph)
    reply_analysis = NetworkAnalyzer().analyze(
        graph,
        relationship_types={RelationshipType.REPLY},
    )

    assert len(collection.posts) == 15
    assert set(graph.nodes) == {post.post_id for post in collection.posts}
    assert relationships
    assert graph.number_of_edges() > 0
    assert isinstance(analysis, GraphAnalysisResult)
    assert analysis.statistics.node_count == len(collection.posts)
    assert analysis.statistics.edge_count == graph.number_of_edges()
    assert reply_analysis.relationship_types == (RelationshipType.REPLY,)
    assert reply_analysis.statistics.node_count == len(collection.posts)
    assert collection == original_collection


def test_real_pipeline_graph_can_be_analyzed_temporally() -> None:
    """The graph produced from sample data is accepted by temporal analysis."""
    collection = LocalJsonPostSource(SAMPLE_FILE).collect()
    relationships = RelationshipBuilder().build(collection)
    graph = NetworkXGraphBuilder().build(collection, relationships)

    result = TemporalNetworkAnalyzer().analyze(graph, timedelta(days=1))

    assert result.windows
    assert all(window.analysis.statistics.node_count >= 0 for window in result.windows)
    assert sum(
        window.analysis.statistics.node_count for window in result.windows
    ) == len(collection.posts)
    assert graph.number_of_nodes() == len(collection.posts)
