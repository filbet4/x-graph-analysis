"""Collect a small, local Scweet sample for offline inspection.

This experiment is deliberately separate from the production application. It
stores Scweet's complete normalized records, including each record's ``raw``
payload, without converting them into project domain models.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from Scweet import Scweet

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "data" / "scweet_sample.json"
AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"


def main() -> None:
    """Collect approximately 100 latest posts for the fixed experiment range."""
    auth_token = os.environ.get(AUTH_TOKEN_ENV)
    if not auth_token:
        raise RuntimeError(
            f"Set {AUTH_TOKEN_ENV} in the current shell before running this script"
        )

    scraper = Scweet(auth_token=auth_token)
    records = scraper.search(
        "artificial intelligence",
        since="2026-10-01",
        until="2026-10-11",
        display_type="Latest",
        limit=100,
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(records)} records to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
