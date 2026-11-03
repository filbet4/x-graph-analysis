"""Preprocessing pipeline boundaries for source-independent post data.

TODO: Implement normalization, deduplication, language handling, and quality checks.
"""

from collections.abc import Sequence

from x_graph_analysis.domain.models import Post
from x_graph_analysis.domain.ports import PostPreprocessor


class NoOpPreprocessor(PostPreprocessor):
    """Explicit placeholder preprocessor for initial composition tests."""

    def process(self, posts: Sequence[Post]) -> Sequence[Post]:
        """Return posts unchanged until preprocessing rules are specified."""
        raise NotImplementedError
