"""Graph analysis strategies and result contracts.

TODO: Add independent analysis strategies and reproducible result models.
"""

from x_graph_analysis.analysis.analyzer import (
    ClusteringCoefficient,
    Community,
    CommunityDetectionResult,
    CommunityMembership,
    CommunityStructuralMetrics,
    ComponentMembership,
    GraphAnalysisResult,
    GraphStatistics,
    NetworkAnalyzer,
    NodeMetrics,
    PageRankScore,
)
from x_graph_analysis.analysis.temporal import (
    TemporalAnalysisError,
    TemporalAnalysisResult,
    TemporalNetworkAnalyzer,
    TemporalWindow,
)

__all__ = [
    "ClusteringCoefficient",
    "Community",
    "CommunityDetectionResult",
    "CommunityMembership",
    "CommunityStructuralMetrics",
    "ComponentMembership",
    "GraphAnalysisResult",
    "GraphStatistics",
    "NetworkAnalyzer",
    "NodeMetrics",
    "PageRankScore",
    "TemporalAnalysisError",
    "TemporalAnalysisResult",
    "TemporalNetworkAnalyzer",
    "TemporalWindow",
]
