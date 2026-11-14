"""Tests for the prospective reaction monitoring experiment."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from experiments.collect_fresh_reaction_posts import collect_once, fresh_record
from experiments.reaction_monitor import (
    MonitoredPost,
    due_observations,
    extract_metrics,
    extract_source_posts,
    load_source_posts,
    run_monitor,
)
from experiments.report_reaction_monitor import (
    aggregate,
    load_successful_events,
    summarize,
    write_csv,
    write_svg,
)

BASE = datetime(2026, 11, 1, 12, tzinfo=UTC)


def source_record(post_id: str = "1") -> dict[str, object]:
    return {
        "tweet_id": post_id,
        "record": {
            "raw": {
                "legacy": {
                    "created_at": "Sun Nov 01 12:00:00 +0000 2026",
                },
            },
        },
    }


def raw_record(post_id: str = "1") -> dict[str, object]:
    return {
        "rest_id": post_id,
        "legacy": {
            "id_str": post_id,
            "created_at": "Sun Nov 01 12:00:00 +0000 2026",
            "favorite_count": 11,
            "reply_count": 3,
            "retweet_count": 4,
            "quote_count": 2,
        },
        "views": {"count": "100"},
    }


class FakeClient:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[list[str]] = []

    def fetch(self, post_ids: list[str]) -> object:
        self.calls.append(post_ids)
        return self.result


def test_source_posts_are_normalized_and_deduplicated() -> None:
    posts = extract_source_posts([source_record(), source_record()])

    assert posts == (MonitoredPost("1", BASE),)


def test_due_observations_use_post_age_and_completed_slots() -> None:
    post = MonitoredPost("1", BASE)

    due = due_observations(
        [post],
        BASE + timedelta(hours=6, minutes=5),
        {("1", 0)},
        ages_hours=(0, 6, 12, 24),
    )

    assert [(item.post.post_id, item.scheduled_age_hours) for item in due] == [
        ("1", 6),
    ]


def test_missing_metrics_are_none_not_zero() -> None:
    metrics = extract_metrics({"rest_id": "1", "legacy": {}})

    assert metrics == {
        "like_count": None,
        "reply_count": None,
        "repost_count": None,
        "quote_count": None,
        "view_count": None,
    }


def test_monitor_appends_observations_and_skips_completed_slots(
    tmp_path: Path,
) -> None:
    history = tmp_path / "observations.jsonl"
    post = MonitoredPost("1", BASE)
    client = FakeClient([raw_record()])

    def clock() -> datetime:
        return BASE + timedelta(hours=6, minutes=5)

    events = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(hours=6, minutes=5),
        delay_seconds=0,
        retries=0,
        clock=clock,
    )

    assert [event["scheduled_age_hours"] for event in events] == [0, 6]
    assert [event["status"] for event in events] == ["skipped_late", "ok"]
    assert events[0]["actual_age_hours"] == round(6 + 5 / 60, 6)
    assert events[1]["actual_age_hours"] == round(6 + 5 / 60, 6)
    assert len(history.read_text(encoding="utf-8").splitlines()) == 2

    second_run = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(hours=6, minutes=5),
        delay_seconds=0,
        retries=0,
        clock=clock,
    )

    assert second_run == ()
    assert len(client.calls) == 1


def test_monitor_records_missing_response_without_marking_slot_complete(
    tmp_path: Path,
) -> None:
    history = tmp_path / "observations.jsonl"
    post = MonitoredPost("1", BASE)
    client = FakeClient([])

    def clock() -> datetime:
        return BASE + timedelta(minutes=5)

    events = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(minutes=5),
        delay_seconds=0,
        retries=0,
        clock=clock,
    )

    assert len(events) == 1
    assert events[0]["status"] == "error"
    assert events[0]["error"] == "post not returned"
    assert all(value is None for value in events[0]["metrics"].values())


def test_thirty_day_old_post_cannot_be_fetched_for_any_slot(
    tmp_path: Path,
) -> None:
    history = tmp_path / "observations.jsonl"
    post = MonitoredPost("1", BASE)
    client = FakeClient([raw_record()])

    events = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(days=30),
        delay_seconds=0,
        retries=0,
        clock=lambda: BASE + timedelta(days=30),
    )

    assert len(events) == 5
    assert all(event["status"] == "skipped_late" for event in events)
    assert client.calls == []


def test_late_initial_slot_is_skipped_without_fetching_history(
    tmp_path: Path,
) -> None:
    history = tmp_path / "observations.jsonl"
    post = MonitoredPost("1", BASE)
    client = FakeClient([raw_record()])

    events = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(minutes=30),
        delay_seconds=0,
        retries=0,
        clock=lambda: BASE + timedelta(minutes=30),
    )

    assert events[0]["scheduled_age_hours"] == 0
    assert events[0]["status"] == "skipped_late"
    assert client.calls == []


def test_fresh_initial_slot_is_active_within_tolerance(
    tmp_path: Path,
) -> None:
    history = tmp_path / "observations.jsonl"
    post = MonitoredPost("1", BASE)
    client = FakeClient([raw_record()])

    events = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(minutes=5),
        delay_seconds=0,
        retries=0,
        clock=lambda: BASE + timedelta(minutes=5),
    )

    assert events[0]["status"] == "ok"
    assert events[0]["actual_age_hours"] == round(5 / 60, 6)
    assert client.calls == [["1"]]


def test_queue_jsonl_is_read_without_manual_conversion(tmp_path: Path) -> None:
    queue = tmp_path / "fresh_posts.jsonl"
    queue.write_text(
        json.dumps(
            {
                "event_type": "post",
                "post_id": "1",
                "published_at": BASE.isoformat(),
                "discovered_at": (BASE + timedelta(minutes=2)).isoformat(),
                "domain": "sport",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert load_source_posts(queue) == (MonitoredPost("1", BASE),)


def test_fresh_collector_filters_and_deduplicates_posts(tmp_path: Path) -> None:
    now = BASE + timedelta(minutes=10)
    fresh = {
        "tweet_id": "1",
        "record": {"raw": {"legacy": {"created_at": "Sun Nov 01 12:05:00 +0000 2026"}}},
    }

    class FakeSearch:
        def search(
            self,
            _query: str,
            **_kwargs: object,
        ) -> list[dict[str, object]]:
            return [fresh]

    queue = tmp_path / "queue.jsonl"
    rejections = tmp_path / "rejections.jsonl"
    first = collect_once(
        FakeSearch(),
        queue,
        rejections,
        now=now,
        lookback_minutes=30,
        delay_seconds=0,
    )
    second = collect_once(
        FakeSearch(),
        queue,
        rejections,
        now=now,
        lookback_minutes=30,
        delay_seconds=0,
    )

    assert first["queued"] == 1
    assert second["queued"] == 0
    assert len(queue.read_text(encoding="utf-8").splitlines()) == 1
    assert (
        fresh_record(
            fresh,
            now=now,
            lookback_minutes=30,
            domain="sport",
            query="test",
        )
        is not None
    )


def test_monitor_retries_transient_network_failure(tmp_path: Path) -> None:
    history = tmp_path / "observations.jsonl"
    post = MonitoredPost("1", BASE)

    class FlakyClient:
        calls = 0

        def fetch(self, post_ids: list[str]) -> list[dict[str, object]]:
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("temporary failure")
            return [raw_record(post_ids[0])]

    client = FlakyClient()
    events = run_monitor(
        [post],
        client,
        history,
        current_time=BASE + timedelta(minutes=5),
        delay_seconds=0,
        retries=1,
        clock=lambda: BASE + timedelta(minutes=5),
    )

    assert events[0]["status"] == "ok"
    assert client.calls == 2


def test_report_summarizes_statuses_and_complete_posts(tmp_path: Path) -> None:
    history = tmp_path / "observations.jsonl"
    events = []
    for age in (0, 6, 12, 24, 48):
        events.append(
            {
                "event_type": "observation",
                "status": "ok",
                "post_id": "1",
                "scheduled_age_hours": age,
                "metrics": {
                    "like_count": age + 1,
                    "reply_count": 1,
                    "repost_count": 2,
                    "quote_count": 3,
                    "view_count": 4,
                },
            }
        )
    events.append(
        {
            "event_type": "observation",
            "status": "skipped_late",
            "post_id": "2",
            "scheduled_age_hours": 0,
            "metrics": dict.fromkeys(
                (
                    "like_count",
                    "reply_count",
                    "repost_count",
                    "quote_count",
                    "view_count",
                )
            ),
        }
    )
    history.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )

    summary = summarize(
        json.loads(line) for line in history.read_text(encoding="utf-8").splitlines()
    )

    assert summary["complete_posts"] == 1
    assert summary["status_counts"] == {"ok": 5, "skipped_late": 1}
    assert summary["reaction_distributions"]["24h.like_count"]["median"] == 25


def test_report_writes_rows_and_svg_without_external_dependencies(
    tmp_path: Path,
) -> None:
    history = tmp_path / "observations.jsonl"
    event = {
        "event_type": "observation",
        "status": "ok",
        "post_id": "1",
        "published_at": BASE.isoformat(),
        "observed_at": (BASE + timedelta(hours=6)).isoformat(),
        "scheduled_age_hours": 6,
        "actual_age_hours": 6.0,
        "metrics": {
            "like_count": 10,
            "reply_count": None,
            "repost_count": 2,
            "quote_count": 1,
            "view_count": 20,
        },
        "missing_metrics": ["reply_count"],
    }
    history.write_text(json.dumps(event) + "\n", encoding="utf-8")
    events = load_successful_events(history)
    summary = aggregate(events)
    csv_path = tmp_path / "report.csv"
    svg_path = tmp_path / "report.svg"

    write_csv(events, csv_path)
    write_svg(summary, svg_path)

    assert summary[6]["like_count"] == 10
    assert "reply_count" in csv_path.read_text(encoding="utf-8")
    assert svg_path.read_text(encoding="utf-8").startswith("<svg")
