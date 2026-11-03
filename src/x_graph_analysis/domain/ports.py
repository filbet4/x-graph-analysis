"""Abstract ports that define the application's replaceable capabilities.

TODO: Refine these contracts after the data model and analysis protocol are agreed.
"""

from abc import ABC, abstractmethod
from collections.abc import Collection, Sequence
from typing import Protocol

from x_graph_analysis.domain.models import (
    Post,
    PostCollection,
    Relationship,
    RelationshipType,
)


class PostSource(ABC):
    """Port for retrieving posts from any external or local data source."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return a stable name for the source implementation."""
        raise NotImplementedError

    @abstractmethod
    def collect(self) -> PostCollection:
        """Collect posts according to source-specific configuration."""
        raise NotImplementedError


class PostPreprocessor(Protocol):
    """Protocol for transforming or filtering source-independent posts."""

    def process(self, posts: Sequence[Post]) -> Sequence[Post]:
        """Return preprocessed posts."""
        ...


class GraphBuilder(Protocol):
    """Protocol for building a graph representation from posts."""

    def build(
        self,
        collection: PostCollection,
        relationships: Sequence[Relationship],
    ) -> object:
        """Build a graph from posts and detected relationships."""
        ...


class GraphAnalyzer(Protocol):
    """Protocol for running an analysis over a graph representation."""

    def analyze(
        self,
        graph: object,
        relationship_types: Collection[RelationshipType] | None = None,
    ) -> object:
        """Analyze a graph with an optional relationship-type filter."""
        ...


class ResultRenderer(Protocol):
    """Protocol for rendering analysis results for a target medium."""

    def render(self, result: object) -> object:
        """Render and return a visualization artifact."""
        ...


class ReportGenerator(Protocol):
    """Protocol for generating reports from analysis outputs."""

    def generate(self, result: object) -> object:
        """Generate and return a report artifact."""
        ...
