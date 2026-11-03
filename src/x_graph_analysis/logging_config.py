"""Standard-library logging configuration for the application.

TODO: Add structured logging, correlation IDs, and deployment-specific sinks.
"""

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure a consistent root logger for command-line execution."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
