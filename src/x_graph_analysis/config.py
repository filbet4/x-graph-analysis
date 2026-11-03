"""Application configuration loaded from explicit environment variables.

TODO: Add validated settings for data sources and analysis runs.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings shared by application composition code."""

    environment: str = "development"
    log_level: str = "INFO"
    neo4j_uri: str = "neo4j://127.0.0.1:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str | None = None
    neo4j_database: str = "xgraph"

    @classmethod
    def from_environment(cls) -> "Settings":
        """Build settings from environment variables with safe defaults."""
        return cls(
            environment=os.getenv("X_GRAPH_ANALYSIS_ENVIRONMENT", "development"),
            log_level=os.getenv("X_GRAPH_ANALYSIS_LOG_LEVEL", "INFO"),
            neo4j_uri=os.getenv(
                "X_GRAPH_ANALYSIS_NEO4J_URI",
                "neo4j://127.0.0.1:7687",
            ),
            neo4j_user=os.getenv(
                "X_GRAPH_ANALYSIS_NEO4J_USER",
                "neo4j",
            ),
            neo4j_password=os.getenv(
                "X_GRAPH_ANALYSIS_NEO4J_PASSWORD",
            ),
            neo4j_database=os.getenv(
                "X_GRAPH_ANALYSIS_NEO4J_DATABASE",
                "xgraph",
            ),
        )