"""Application-level orchestration boundaries for analysis workflows.

TODO: Implement explicit use cases once the thesis workflow and persistence
needs are known.
"""

from dataclasses import dataclass

from x_graph_analysis.domain.ports import (
    GraphAnalyzer,
    GraphBuilder,
    PostPreprocessor,
    PostSource,
    ReportGenerator,
    ResultRenderer,
)


@dataclass(frozen=True, slots=True)
class AnalysisPipeline:
    """Coordinates replaceable stages without owning their implementation."""

    source: PostSource
    preprocessor: PostPreprocessor
    graph_builder: GraphBuilder
    analyzer: GraphAnalyzer
    renderer: ResultRenderer
    report_generator: ReportGenerator

    def run(self) -> object:
        """Execute the configured workflow.

        The sequence is intentionally left unspecified until domain semantics
        are settled.
        """
        raise NotImplementedError
