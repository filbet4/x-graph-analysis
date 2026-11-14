"""Run one non-overlapping fresh collection and monitoring cycle."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from .collect_fresh_reaction_posts import (
        DEFAULT_DELAY_SECONDS,
        DEFAULT_LIMIT_PER_QUERY,
        DEFAULT_LOOKBACK_MINUTES,
        DEFAULT_QUEUE_PATH,
        DEFAULT_REJECTION_PATH,
        DEFAULT_RETRIES,
        collect_once,
        create_client,
    )
    from .reaction_monitor import (
        load_source_posts,
        run_monitor,
    )
except ImportError:
    from collect_fresh_reaction_posts import (
        DEFAULT_DELAY_SECONDS,
        DEFAULT_LIMIT_PER_QUERY,
        DEFAULT_LOOKBACK_MINUTES,
        DEFAULT_QUEUE_PATH,
        DEFAULT_REJECTION_PATH,
        DEFAULT_RETRIES,
        collect_once,
        create_client,
    )
    from reaction_monitor import (
        load_source_posts,
        run_monitor,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HISTORY_PATH = PROJECT_ROOT / "runs" / "reaction_observations.jsonl"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "runs" / "reaction_cycle.lock"
DEFAULT_LOG_PATH = PROJECT_ROOT / "runs" / "reaction_cycle.log.jsonl"
STALE_LOCK_SECONDS = 6 * 60 * 60


def now_utc() -> datetime:
    """Return current UTC time."""
    return datetime.now(UTC)


def log_event(path: Path, event: dict[str, Any]) -> None:
    """Append one structured cycle log event."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output_file:
        output_file.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        output_file.flush()
        os.fsync(output_file.fileno())


@contextmanager
def cycle_lock(path: Path) -> Iterator[bool]:
    """Acquire an exclusive lock and recover only old stale locks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            lock_age = time.time() - path.stat().st_mtime
            if lock_age < STALE_LOCK_SECONDS:
                yield False
                return
            path.unlink(missing_ok=True)
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(
            descriptor,
            json.dumps(
                {"pid": os.getpid(), "started_at": now_utc().isoformat()},
                ensure_ascii=False,
            ).encode("utf-8"),
        )
        yield True
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if descriptor is not None:
            path.unlink(missing_ok=True)


class ScweetInfoAdapter:
    """Adapt one Scweet instance to the monitor's fetch protocol."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def fetch(self, post_ids: list[str]) -> object:
        return self._client.get_tweet_info(
            tweet_ids=post_ids,
            raw_json=True,
            save=False,
        )


def run_cycle(
    *,
    queue_path: Path = DEFAULT_QUEUE_PATH,
    rejection_path: Path = DEFAULT_REJECTION_PATH,
    history_path: Path = DEFAULT_HISTORY_PATH,
    lock_path: Path = DEFAULT_LOCK_PATH,
    log_path: Path = DEFAULT_LOG_PATH,
    lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    limit_per_query: int = DEFAULT_LIMIT_PER_QUERY,
    retries: int = DEFAULT_RETRIES,
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
    tolerance_minutes: int = 15,
    dry_run: bool = False,
    client_factory: Callable[[str], Any] = create_client,
    clock: Callable[[], datetime] = now_utc,
) -> dict[str, Any]:
    """Run collector first and monitor second, or report a dry-run plan."""
    started_at = clock().astimezone(UTC)
    with cycle_lock(lock_path) as acquired:
        if not acquired:
            result = {
                "status": "skipped_locked",
                "started_at": started_at.isoformat(),
            }
            log_event(log_path, result)
            return result
        log_event(
            log_path,
            {"status": "started", "started_at": started_at.isoformat()},
        )
        try:
            if dry_run:
                collector = {
                    "queries": 17,
                    "lookback_minutes": lookback_minutes,
                    "limit_per_query": limit_per_query,
                    "network": False,
                }
                monitor_posts = (
                    load_source_posts(queue_path) if queue_path.exists() else ()
                )
                monitor_events = run_monitor(
                    monitor_posts,
                    _NoNetworkClient(),
                    history_path,
                    current_time=clock(),
                    dry_run=True,
                    tolerance_minutes=tolerance_minutes,
                )
            else:
                token = os.environ.get("SCWEET_AUTH_TOKEN", "").strip()
                if not token:
                    raise RuntimeError("SCWEET_AUTH_TOKEN is required")
                client = client_factory(token)
                collector = collect_once(
                    client,
                    queue_path,
                    rejection_path,
                    now=clock(),
                    lookback_minutes=lookback_minutes,
                    limit_per_query=limit_per_query,
                    retries=retries,
                    delay_seconds=delay_seconds,
                )
                monitor_posts = load_source_posts(queue_path)
                monitor_events = run_monitor(
                    monitor_posts,
                    ScweetInfoAdapter(client),
                    history_path,
                    current_time=clock(),
                    retries=retries,
                    delay_seconds=delay_seconds,
                    tolerance_minutes=tolerance_minutes,
                )
            status_counts: dict[str, int] = {}
            for event in monitor_events:
                status = str(event.get("status", "unknown"))
                status_counts[status] = status_counts.get(status, 0) + 1
            finished_at = clock().astimezone(UTC)
            result = {
                "status": "dry_run" if dry_run else "finished",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_seconds": round(
                    (finished_at - started_at).total_seconds(),
                    3,
                ),
                "collector": collector,
                "monitor": {
                    "posts": len(monitor_posts),
                    "events": len(monitor_events),
                    "status_counts": status_counts,
                },
            }
            log_event(log_path, result)
            return result
        except Exception as error:
            finished_at = clock().astimezone(UTC)
            result = {
                "status": "error",
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_seconds": round(
                    (finished_at - started_at).total_seconds(),
                    3,
                ),
                "error": f"{type(error).__name__}: {error}",
            }
            log_event(log_path, result)
            return result


class _NoNetworkClient:
    def fetch(self, _post_ids: list[str]) -> object:
        raise RuntimeError("network disabled in dry-run")


def main() -> None:
    """Run one cycle; schedule this command every five minutes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--rejections", type=Path, default=DEFAULT_REJECTION_PATH)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY_PATH)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument(
        "--lookback-minutes", type=int, default=DEFAULT_LOOKBACK_MINUTES
    )
    parser.add_argument("--limit-per-query", type=int, default=DEFAULT_LIMIT_PER_QUERY)
    parser.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    parser.add_argument("--delay-seconds", type=float, default=DEFAULT_DELAY_SECONDS)
    parser.add_argument("--tolerance-minutes", type=int, default=15)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = run_cycle(
        queue_path=args.queue,
        rejection_path=args.rejections,
        history_path=args.history,
        lock_path=args.lock,
        log_path=args.log,
        lookback_minutes=args.lookback_minutes,
        limit_per_query=args.limit_per_query,
        retries=args.retries,
        delay_seconds=args.delay_seconds,
        tolerance_minutes=args.tolerance_minutes,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
