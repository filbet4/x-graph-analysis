"""Collect fresh X posts for prospective reaction monitoring."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .reaction_monitor import extract_post_id, extract_published_at
except ImportError:
    from reaction_monitor import extract_post_id, extract_published_at


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "runs" / "fresh_reaction_posts.jsonl"
DEFAULT_REJECTION_PATH = PROJECT_ROOT / "runs" / "fresh_reaction_rejections.jsonl"
AUTH_TOKEN_ENV = "SCWEET_AUTH_TOKEN"
DEFAULT_LOOKBACK_MINUTES = 30
DEFAULT_LIMIT_PER_QUERY = 50
DEFAULT_RETRIES = 2
DEFAULT_DELAY_SECONDS = 2.0

QUERIES: dict[str, tuple[str, ...]] = {
    "politics": (
        "Donald Tusk lang:pl",
        "Karol Nawrocki lang:pl",
        "Prawo i Sprawiedliwość lang:pl",
        "Konfederacja lang:pl",
        "Sejm lang:pl",
    ),
    "sport": (
        "Iga Świątek lang:pl",
        "Robert Lewandowski lang:pl",
        "reprezentacja Polski lang:pl",
        "Ekstraklasa lang:pl",
        "polska siatkówka lang:pl",
    ),
    "pop_culture": (
        "Friz Ekipa lang:pl",
        "Mata raper lang:pl",
        "Taco Hemingway lang:pl",
        "Quebonafide lang:pl",
        "Bedoes lang:pl",
        "polski rap lang:pl",
        "FAME MMA lang:pl",
    ),
}


def now_utc() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def normalize_search_result(result: object) -> tuple[dict[str, Any], ...]:
    """Normalize common Scweet Search result shapes."""
    if isinstance(result, list):
        return tuple(item for item in result if isinstance(item, dict))
    if isinstance(result, dict):
        return (result,)
    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        try:
            records = to_dict(orient="records")
        except (TypeError, ValueError):
            return ()
        if isinstance(records, list):
            return tuple(item for item in records if isinstance(item, dict))
    return ()


def query_bounds(now: datetime, lookback_minutes: int) -> tuple[str, str]:
    """Return date bounds broad enough for Scweet, then filter by exact time."""
    if lookback_minutes <= 0:
        raise ValueError("lookback_minutes must be positive")
    current = now.astimezone(UTC)
    start = current - timedelta(minutes=lookback_minutes, days=1)
    end = current + timedelta(days=1)
    return start.date().isoformat(), end.date().isoformat()


def fresh_record(
    record: Mapping[str, Any],
    *,
    now: datetime,
    lookback_minutes: int,
    domain: str,
    query: str,
) -> dict[str, Any] | None:
    """Convert a Search record to a queue event when it is fresh."""
    post_id = extract_post_id(record)
    if post_id is None:
        return None
    published_at = extract_published_at(record)
    current = now.astimezone(UTC)
    age = current - published_at
    if age < timedelta(0) or age > timedelta(minutes=lookback_minutes):
        return None
    return {
        "event_type": "post",
        "post_id": post_id,
        "published_at": published_at.isoformat(),
        "discovered_at": current.isoformat(),
        "actual_age_minutes": round(age.total_seconds() / 60, 6),
        "domain": domain,
        "query": query,
    }


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    """Append one durable JSONL record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output_file:
        output_file.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        output_file.flush()
        os.fsync(output_file.fileno())


def existing_post_ids(path: Path) -> set[str]:
    """Read successfully queued post IDs, tolerating interrupted lines."""
    if not path.exists():
        return set()
    post_ids: set[str] = set()
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("event_type", "post") == "post" and record.get("post_id"):
                post_ids.add(str(record["post_id"]))
    return post_ids


def collect_once(
    client: Any,
    queue_path: Path,
    rejection_path: Path,
    *,
    now: datetime,
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    limit_per_query: int = DEFAULT_LIMIT_PER_QUERY,
    retries: int = DEFAULT_RETRIES,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    dry_run: bool = False,
) -> dict[str, int]:
    """Run one bounded Search cycle and append only fresh unique posts."""
    if limit_per_query <= 0 or retries < 0 or delay_seconds < 0:
        raise ValueError("invalid collector limits")
    since, until = query_bounds(now, lookback_minutes)
    queued_ids = existing_post_ids(queue_path)
    counters = {"queries": 0, "returned": 0, "fresh": 0, "queued": 0, "errors": 0}

    for domain, queries in QUERIES.items():
        for query in queries:
            counters["queries"] += 1
            if dry_run:
                continue
            result: object | None = None
            last_error: str | None = None
            for attempt in range(retries + 1):
                try:
                    result = client.search(
                        query,
                        since=since,
                        until=until,
                        display_type="Latest",
                        limit=limit_per_query,
                    )
                    last_error = None
                    break
                except Exception as error:
                    last_error = f"{type(error).__name__}: {error}"
                    if attempt < retries:
                        time.sleep(delay_seconds * (2**attempt))
            if last_error is not None:
                counters["errors"] += 1
                append_jsonl(
                    rejection_path,
                    {
                        "event_type": "query_error",
                        "observed_at": now.astimezone(UTC).isoformat(),
                        "domain": domain,
                        "query": query,
                        "error": last_error,
                    },
                )
                continue
            records = normalize_search_result(result)
            counters["returned"] += len(records)
            for record in records:
                try:
                    event = fresh_record(
                        record,
                        now=now,
                        lookback_minutes=lookback_minutes,
                        domain=domain,
                        query=query,
                    )
                except ValueError as error:
                    append_jsonl(
                        rejection_path,
                        {
                            "event_type": "rejected",
                            "observed_at": now.astimezone(UTC).isoformat(),
                            "domain": domain,
                            "query": query,
                            "reason": str(error),
                        },
                    )
                    continue
                if event is None:
                    continue
                counters["fresh"] += 1
                post_id = str(event["post_id"])
                if post_id in queued_ids:
                    continue
                append_jsonl(queue_path, event)
                queued_ids.add(post_id)
                counters["queued"] += 1
            if delay_seconds:
                time.sleep(delay_seconds)
    return counters


def create_client(auth_token: str) -> Any:
    """Create Scweet lazily so dry-run never imports or contacts the service."""
    from Scweet import Scweet

    return Scweet(auth_token=auth_token)


def main() -> None:
    """Run one fresh-post collection cycle."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--rejections", type=Path, default=DEFAULT_REJECTION_PATH)
    parser.add_argument(
        "--lookback-minutes",
        type=int,
        default=DEFAULT_LOOKBACK_MINUTES,
    )
    parser.add_argument("--limit-per-query", type=int, default=DEFAULT_LIMIT_PER_QUERY)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.dry_run:
        since, until = query_bounds(now_utc(), args.lookback_minutes)
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "queries": sum(len(queries) for queries in QUERIES.values()),
                    "since": since,
                    "until": until,
                    "lookback_minutes": args.lookback_minutes,
                    "queue": str(args.queue),
                },
                indent=2,
            )
        )
        return
    token = os.environ.get(AUTH_TOKEN_ENV)
    if not token:
        raise SystemExit(f"{AUTH_TOKEN_ENV} is required unless --dry-run is used")
    counters = collect_once(
        create_client(token),
        args.queue,
        args.rejections,
        now=now_utc(),
        lookback_minutes=args.lookback_minutes,
        limit_per_query=args.limit_per_query,
        retries=args.retries,
        delay_seconds=args.delay_seconds,
    )
    print(json.dumps(counters, indent=2))


if __name__ == "__main__":
    main()
