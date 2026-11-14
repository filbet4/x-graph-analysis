"""Prospective, age-aligned monitoring of X post reactions."""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

OBSERVATION_AGES_HOURS = (0, 6, 12, 24, 48)
METRIC_NAMES = (
    "like_count",
    "reply_count",
    "repost_count",
    "quote_count",
    "view_count",
)


class TweetInfoClient(Protocol):
    """Protocol implemented by the Scweet client adapter and test doubles."""

    def fetch(self, post_ids: Sequence[str]) -> object:
        """Fetch raw tweet records for the requested post IDs."""


@dataclass(frozen=True, slots=True)
class MonitoredPost:
    """Post identity and publication time used by the schedule."""

    post_id: str
    published_at: datetime


@dataclass(frozen=True, slots=True)
class DueObservation:
    """One observation slot that is ready to be collected."""

    post: MonitoredPost
    scheduled_age_hours: int
    due_at: datetime


@dataclass(frozen=True, slots=True)
class SkippedObservation:
    """An age slot that was missed and must never be fetched retroactively."""

    post: MonitoredPost
    scheduled_age_hours: int
    due_at: datetime


class ScweetTweetInfoClient:
    """Lazy adapter around Scweet's batch ``get_tweet_info`` call."""

    def __init__(self, auth_token: str) -> None:
        if not auth_token:
            raise ValueError("auth_token must be non-empty")
        from Scweet import Scweet

        self._client = Scweet(auth_token=auth_token)

    def fetch(self, post_ids: Sequence[str]) -> object:
        """Fetch raw records without allowing Scweet to write files."""
        return self._client.get_tweet_info(
            tweet_ids=list(post_ids),
            raw_json=True,
            save=False,
        )


def now_utc() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


def parse_datetime(value: object) -> datetime:
    """Parse the timestamp formats used by the repository's Scweet records."""
    if not value:
        raise ValueError("missing timestamp")
    text = str(value)
    formats = (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
    )
    for date_format in formats:
        try:
            parsed = datetime.strptime(text, date_format)
        except ValueError:
            continue
        return parsed.astimezone(UTC)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"unsupported timestamp: {text}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(UTC)


def _legacy(record: Mapping[str, Any]) -> Mapping[str, Any]:
    value = record.get("legacy")
    return value if isinstance(value, Mapping) else {}


def extract_post_id(record: Mapping[str, Any]) -> str | None:
    """Extract a post ID from a Search wrapper or raw tweet record."""
    value = record.get("post_id") or record.get("tweet_id") or record.get("rest_id")
    if value is None and isinstance(record.get("record"), Mapping):
        nested = record["record"]
        value = nested.get("tweet_id") or nested.get("rest_id")
    if value is None:
        value = _legacy(record).get("id_str")
    return str(value) if value else None


def extract_published_at(record: Mapping[str, Any]) -> datetime:
    """Extract a post publication timestamp from a source or raw record."""
    candidates: list[object] = []
    nested = record.get("record")
    if isinstance(nested, Mapping):
        raw = nested.get("raw")
        if isinstance(raw, Mapping):
            candidates.append(_legacy(raw).get("created_at"))
        candidates.extend((nested.get("timestamp"), nested.get("created_at")))
    candidates.append(_legacy(record).get("created_at"))
    candidates.extend(
        (
            record.get("published_at"),
            record.get("timestamp"),
            record.get("created_at"),
        )
    )
    for candidate in candidates:
        if candidate:
            return parse_datetime(candidate)
    raise ValueError("post does not contain a publication timestamp")


def extract_source_posts(
    records: Iterable[Mapping[str, Any]],
) -> tuple[MonitoredPost, ...]:
    """Normalize source records and reject duplicate post identities."""
    posts: dict[str, MonitoredPost] = {}
    for record in records:
        post_id = extract_post_id(record)
        if post_id is None:
            continue
        post = MonitoredPost(post_id, extract_published_at(record))
        previous = posts.get(post_id)
        if previous is not None and previous.published_at != post.published_at:
            raise ValueError(f"conflicting publication times for {post_id}")
        posts[post_id] = post
    return tuple(posts[post_id] for post_id in sorted(posts))


def load_source_posts(path: Path) -> tuple[MonitoredPost, ...]:
    """Load posts from a collector JSON without changing that file."""
    if path.suffix.lower() == ".jsonl":
        records: list[object] = []
        with path.open(encoding="utf-8") as input_file:
            for line in input_file:
                if line.strip():
                    records.append(json.loads(line))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            records = data
        elif isinstance(data, Mapping):
            records = data.get("records", [])
        else:
            raise ValueError("source JSON must contain a records list")
    if not isinstance(records, list):
        raise ValueError("source JSON field 'records' must be a list")
    mappings = [record for record in records if isinstance(record, Mapping)]
    return extract_source_posts(mappings)


def due_observations(
    posts: Iterable[MonitoredPost],
    observed_at: datetime,
    completed_slots: set[tuple[str, int]],
    ages_hours: Sequence[int] = OBSERVATION_AGES_HOURS,
    tolerance_minutes: int = 15,
) -> tuple[DueObservation, ...]:
    """Return only age slots currently inside their collection tolerance."""
    due, _ = scheduled_observations(
        posts,
        observed_at,
        completed_slots,
        ages_hours=ages_hours,
        tolerance_minutes=tolerance_minutes,
    )
    return due


def scheduled_observations(
    posts: Iterable[MonitoredPost],
    observed_at: datetime,
    completed_slots: set[tuple[str, int]],
    ages_hours: Sequence[int] = OBSERVATION_AGES_HOURS,
    tolerance_minutes: int = 15,
) -> tuple[tuple[DueObservation, ...], tuple[SkippedObservation, ...]]:
    """Return active slots and permanently missed slots separately."""
    if tolerance_minutes < 0:
        raise ValueError("tolerance_minutes must be non-negative")
    current = observed_at.astimezone(UTC)
    due: list[DueObservation] = []
    skipped: list[SkippedObservation] = []
    for post in posts:
        for age_hours in ages_hours:
            key = (post.post_id, age_hours)
            due_at = post.published_at + timedelta(hours=age_hours)
            if key in completed_slots or current < due_at:
                continue
            if current > due_at + timedelta(minutes=tolerance_minutes):
                skipped.append(SkippedObservation(post, age_hours, due_at))
            else:
                due.append(DueObservation(post, age_hours, due_at))
    return (
        tuple(sorted(due, key=lambda item: (item.due_at, item.post.post_id))),
        tuple(sorted(skipped, key=lambda item: (item.due_at, item.post.post_id))),
    )


def normalize_result(result: object) -> tuple[dict[str, Any], ...]:
    """Normalize list, dict, wrapper, and dataframe-like Scweet results."""
    if result is None:
        return ()
    if isinstance(result, list):
        return tuple(item for item in result if isinstance(item, dict))
    if isinstance(result, dict):
        for key in ("records", "tweets", "data"):
            value = result.get(key)
            if isinstance(value, list):
                return tuple(item for item in value if isinstance(item, dict))
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


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def extract_metrics(record: Mapping[str, Any]) -> dict[str, int | None]:
    """Extract only counters actually present in a raw Scweet record."""
    legacy = _legacy(record)
    views = record.get("views")
    view_value = views.get("count") if isinstance(views, Mapping) else None
    return {
        "like_count": _optional_int(legacy.get("favorite_count", record.get("likes"))),
        "reply_count": _optional_int(legacy.get("reply_count", record.get("replies"))),
        "repost_count": _optional_int(
            legacy.get("retweet_count", record.get("retweets"))
        ),
        "quote_count": _optional_int(legacy.get("quote_count", record.get("quotes"))),
        "view_count": _optional_int(
            view_value if view_value is not None else record.get("views")
        ),
    }


def observation_record(
    due: DueObservation,
    observed_at: datetime,
    raw_record: Mapping[str, Any] | None,
    *,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one append-only observation event."""
    actual_age = (
        observed_at.astimezone(UTC) - due.post.published_at
    ).total_seconds() / 3600
    metrics = (
        extract_metrics(raw_record)
        if raw_record is not None
        else dict.fromkeys(METRIC_NAMES)
    )
    return {
        "event_type": "observation",
        "post_id": due.post.post_id,
        "published_at": due.post.published_at.isoformat(),
        "observed_at": observed_at.astimezone(UTC).isoformat(),
        "scheduled_age_hours": due.scheduled_age_hours,
        "actual_age_hours": round(actual_age, 6),
        "status": status,
        "metrics": metrics,
        "missing_metrics": [name for name, value in metrics.items() if value is None],
        "error": error,
    }


def terminal_slots(path: Path) -> set[tuple[str, int]]:
    """Read successful and permanently skipped slots from JSONL history."""
    if not path.exists():
        return set()
    completed: set[tuple[str, int]] = set()
    with path.open(encoding="utf-8") as input_file:
        for line in input_file:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                event.get("status") in {"ok", "skipped_late"}
                and event.get("post_id") is not None
            ):
                completed.add(
                    (str(event["post_id"]), int(event["scheduled_age_hours"]))
                )
    return completed


def append_event(path: Path, event: Mapping[str, Any]) -> None:
    """Append one JSON event and flush it durably before continuing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as output_file:
        output_file.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        output_file.flush()
        os.fsync(output_file.fileno())


def run_monitor(
    posts: Iterable[MonitoredPost],
    client: TweetInfoClient,
    history_path: Path,
    *,
    current_time: datetime | None = None,
    batch_size: int = 50,
    delay_seconds: float = 2.0,
    retries: int = 2,
    dry_run: bool = False,
    clock: Callable[[], datetime] = now_utc,
    ages_hours: Sequence[int] = OBSERVATION_AGES_HOURS,
    tolerance_minutes: int = 15,
) -> tuple[dict[str, Any], ...]:
    """Collect due observations, preserving every attempt in JSONL."""
    if batch_size <= 0 or retries < 0 or delay_seconds < 0:
        raise ValueError("batch_size, retries, and delay_seconds are invalid")
    now = (current_time or now_utc()).astimezone(UTC)
    due, skipped = scheduled_observations(
        posts,
        now,
        terminal_slots(history_path),
        ages_hours=ages_hours,
        tolerance_minutes=tolerance_minutes,
    )
    if dry_run:
        planned = tuple(
            {
                "post_id": item.post.post_id,
                "scheduled_age_hours": item.scheduled_age_hours,
                "due_at": item.due_at.isoformat(),
                "status": "due",
            }
            for item in due
        )
        return planned + tuple(
            {
                "post_id": item.post.post_id,
                "scheduled_age_hours": item.scheduled_age_hours,
                "due_at": item.due_at.isoformat(),
                "status": "skipped_late",
            }
            for item in skipped
        )
    events: list[dict[str, Any]] = []
    observed_at = clock().astimezone(UTC)
    for item in skipped:
        event = observation_record(
            DueObservation(item.post, item.scheduled_age_hours, item.due_at),
            observed_at,
            None,
            status="skipped_late",
            error="observation slot exceeded tolerance",
        )
        append_event(history_path, event)
        events.append(event)
    for start in range(0, len(due), batch_size):
        batch = due[start : start + batch_size]
        requested = [item.post.post_id for item in batch]
        result: object | None = None
        last_error: str | None = None
        for attempt in range(retries + 1):
            try:
                result = client.fetch(requested)
                last_error = None
                break
            except Exception as error:
                last_error = f"{type(error).__name__}: {error}"
                if attempt < retries:
                    time.sleep(delay_seconds * (2**attempt))
        records = {
            extract_post_id(record): record for record in normalize_result(result)
        }
        observed_at = clock().astimezone(UTC)
        for item in batch:
            raw = records.get(item.post.post_id)
            status = "ok" if raw is not None and last_error is None else "error"
            event = observation_record(
                item,
                observed_at,
                raw,
                status=status,
                error=None if status == "ok" else last_error or "post not returned",
            )
            append_event(history_path, event)
            events.append(event)
        if start + batch_size < len(due) and delay_seconds:
            time.sleep(delay_seconds)
    return tuple(events)


def _records_from_source(path: Path) -> tuple[MonitoredPost, ...]:
    return load_source_posts(path)


def main() -> None:
    """Run a dry schedule or an explicitly enabled Scweet collection."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--delay-seconds", type=float, default=2.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--tolerance-minutes", type=int, default=15)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only-age", type=int, choices=OBSERVATION_AGES_HOURS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.execute and args.dry_run:
        parser.error("--execute and --dry-run are mutually exclusive")
    posts = _records_from_source(args.source)
    if args.limit is not None:
        if args.limit <= 0:
            parser.error("--limit must be positive")
        posts = posts[: args.limit]
    ages_hours = (
        (args.only_age,) if args.only_age is not None else OBSERVATION_AGES_HOURS
    )
    if not args.execute:
        args.dry_run = True
    if args.execute:
        token = os.environ.get("SCWEET_AUTH_TOKEN")
        if not token:
            raise SystemExit("SCWEET_AUTH_TOKEN is required for --execute")
        client: TweetInfoClient = ScweetTweetInfoClient(token)
    else:

        class NoNetworkClient:
            def fetch(self, _post_ids: Sequence[str]) -> object:
                raise RuntimeError("network disabled in dry-run mode")

        client = NoNetworkClient()
    result = run_monitor(
        posts,
        client,
        args.history,
        batch_size=args.batch_size,
        delay_seconds=args.delay_seconds,
        retries=args.retries,
        dry_run=args.dry_run,
        ages_hours=ages_hours,
        tolerance_minutes=args.tolerance_minutes,
    )
    print(
        json.dumps(
            {
                "posts": len(posts),
                "events": len(result),
                "status_counts": dict(
                    Counter(str(event.get("status", "unknown")) for event in result)
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
