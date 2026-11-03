"""Report generation implementations behind the report port.

TODO: Implement report templates, artifact storage, and provenance information.
"""

from x_graph_analysis.domain.ports import ReportGenerator


class ThesisReportGenerator(ReportGenerator):
    """Placeholder generator for thesis-oriented analysis reports."""

    def generate(self, result: object) -> object:
        """Generate a report after the required report contract is agreed."""
        raise NotImplementedError
