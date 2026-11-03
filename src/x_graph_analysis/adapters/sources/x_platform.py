"""Placeholder adapter boundary for collecting posts from the X platform.

TODO: Implement authenticated collection, pagination, rate-limit handling, and
source mapping.
"""

from x_graph_analysis.domain.models import PostCollection
from x_graph_analysis.domain.ports import PostSource


class XPlatformSource(PostSource):
    """Future X platform implementation of the generic post-source port."""

    @property
    def name(self) -> str:
        """Return the adapter's stable source name."""
        return "x-platform"

    def collect(self) -> PostCollection:
        """Collect posts from X after the integration contract is defined."""
        raise NotImplementedError
