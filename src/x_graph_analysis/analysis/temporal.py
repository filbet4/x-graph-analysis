"""Fixed-window temporal analysis delegated to the structural analyzer.

TODO: Add alternative windowing strategies only after the fixed-window baseline
has been evaluated for the thesis methodology.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import networkx as nx

from x_graph_analysis.analysis.analyzer import GraphAnalysisResult, NetworkAnalyzer
from x_graph_analysis.domain.models import RelationshipType


class TemporalAnalysisError(ValueError):
    """Raised when temporal graph input or configuration is invalid."""


@dataclass(frozen=True, slots=True)
class TemporalWindow:
    """One half-open temporal window and its delegated graph analysis."""

    start: datetime
    end: datetime
    analysis: GraphAnalysisResult


@dataclass(frozen=True, slots=True)
class TemporalAnalysisResult:
    """Chronologically ordered analyses for fixed temporal windows."""

    window_size: timedelta
    start: datetime | None
    end: datetime | None
    windows: tuple[TemporalWindow, ...]


class TemporalNetworkAnalyzer:
    """Partition a graph by node timestamps and delegate each window analysis."""

    def __init__(self, analyzer: NetworkAnalyzer | None = None) -> None:
        """Create a temporal analyzer using the supplied structural analyzer."""
        self._analyzer = analyzer or NetworkAnalyzer()

    def analyze(
        self,
        graph: object,
        window_size: timedelta,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        relationship_types: Collection[RelationshipType] | None = None,
    ) -> TemporalAnalysisResult:
        """Analyze induced fixed-duration windows over timestamped graph nodes."""
        if not isinstance(graph, nx.MultiDiGraph):
            raise TemporalAnalysisError(
                "Temporal analysis requires a NetworkX MultiDiGraph"
            )
        self._validate_window_size(window_size)
        self._validate_optional_timestamp(start, "start")
        self._validate_optional_timestamp(end, "end")
        if start is not None and end is not None and start >= end:
            raise TemporalAnalysisError("start must be before end")

        timestamps = self._timestamps(graph)
        if not timestamps:
            range_start: datetime | None
            range_end: datetime | None
            if start is not None and end is not None:
                range_start, range_end = start, end
            else:
                range_start = range_end = None
            return TemporalAnalysisResult(
                window_size=window_size,
                start=range_start,
                end=range_end,
                windows=self._empty_graph_windows(
                    graph,
                    window_size,
                    range_start,
                    range_end,
                    relationship_types,
                ),
            )

        range_start = start or min(timestamps.values())
        range_end = end or self._derived_end(
            range_start, max(timestamps.values()), window_size
        )
        if range_start >= range_end:
            raise TemporalAnalysisError("start must be before end")
        outside = [
            timestamp
            for timestamp in timestamps.values()
            if timestamp < range_start or timestamp >= range_end
        ]
        if outside:
            raise TemporalAnalysisError(
                "all post timestamps must fall within the analysis [start, end) range"
            )

        windows = tuple(
            self._analyze_window(
                graph,
                timestamps,
                window_start,
                min(window_start + window_size, range_end),
                relationship_types,
            )
            for window_start in self._window_starts(range_start, range_end, window_size)
        )
        return TemporalAnalysisResult(
            window_size=window_size,
            start=range_start,
            end=range_end,
            windows=windows,
        )

    @staticmethod
    def _validate_window_size(window_size: timedelta) -> None:
        if not isinstance(window_size, timedelta):
            raise TypeError("window_size must be a datetime.timedelta")
        if window_size <= timedelta(0):
            raise TemporalAnalysisError("window_size must be positive")

    @staticmethod
    def _validate_optional_timestamp(
        timestamp: datetime | None,
        name: str,
    ) -> None:
        if timestamp is not None and (
            timestamp.tzinfo is None or timestamp.utcoffset() is None
        ):
            raise TemporalAnalysisError(f"{name} must be timezone-aware")

    @staticmethod
    def _timestamps(graph: nx.MultiDiGraph[Any, Any]) -> dict[Any, datetime]:
        timestamps: dict[Any, datetime] = {}
        for node, attributes in graph.nodes(data=True):
            timestamp = attributes.get("created_at")
            if not isinstance(timestamp, datetime):
                raise TemporalAnalysisError(
                    f"node {node!r} has a missing or invalid created_at timestamp"
                )
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise TemporalAnalysisError(
                    f"node {node!r} created_at must be timezone-aware"
                )
            timestamps[node] = timestamp
        return timestamps

    @staticmethod
    def _derived_end(
        start: datetime,
        latest: datetime,
        window_size: timedelta,
    ) -> datetime:
        elapsed = latest - start
        window_count = elapsed // window_size + 1
        return start + window_count * window_size

    @staticmethod
    def _window_starts(
        start: datetime,
        end: datetime,
        window_size: timedelta,
    ) -> tuple[datetime, ...]:
        starts: list[datetime] = []
        current = start
        while current < end:
            starts.append(current)
            current += window_size
        return tuple(starts)

    def _analyze_window(
        self,
        graph: nx.MultiDiGraph[Any, Any],
        timestamps: dict[Any, datetime],
        start: datetime,
        end: datetime,
        relationship_types: Collection[RelationshipType] | None,
    ) -> TemporalWindow:
        nodes = [node for node in graph.nodes if start <= timestamps[node] < end]
        subgraph = graph.subgraph(nodes).copy()
        analysis = self._analyzer.analyze(
            subgraph,
            relationship_types=relationship_types,
        )
        return TemporalWindow(start=start, end=end, analysis=analysis)

    def _empty_graph_windows(
        self,
        graph: nx.MultiDiGraph[Any, Any],
        window_size: timedelta,
        start: datetime | None,
        end: datetime | None,
        relationship_types: Collection[RelationshipType] | None,
    ) -> tuple[TemporalWindow, ...]:
        if start is None or end is None:
            return ()
        empty_timestamps = dict.fromkeys(graph.nodes, start)
        return tuple(
            self._analyze_window(
                graph,
                empty_timestamps,
                window_start,
                min(window_start + window_size, end),
                relationship_types,
            )
            for window_start in self._window_starts(start, end, window_size)
        )
