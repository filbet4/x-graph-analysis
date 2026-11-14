"""Tests for the non-overlapping reaction cycle runner."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from experiments.run_reaction_cycle import run_cycle

BASE = datetime(2026, 11, 6, 12, tzinfo=UTC)


def queue_record() -> dict[str, object]:
    return {
        "event_type": "post",
        "post_id": "1",
        "published_at": BASE.isoformat(),
        "discovered_at": (BASE + timedelta(minutes=1)).isoformat(),
        "domain": "sport",
    }


class FakeScweet:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str, **_kwargs: object) -> list[dict[str, object]]:
        self.calls.append(f"search:{query}")
        return []

    def get_tweet_info(self, **_kwargs: object) -> list[dict[str, object]]:
        self.calls.append("get_tweet_info")
        return [
            {
                "rest_id": "1",
                "legacy": {
                    "id_str": "1",
                    "favorite_count": 4,
                    "reply_count": 1,
                    "retweet_count": 2,
                    "quote_count": 0,
                },
                "views": {"count": "10"},
            }
        ]


def test_cycle_runs_collector_before_monitor_and_logs_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    queue = tmp_path / "queue.jsonl"
    queue.write_text(json.dumps(queue_record()) + "\n", encoding="utf-8")
    client = FakeScweet()
    monkeypatch.setenv("SCWEET_AUTH_TOKEN", "test-token")

    result = run_cycle(
        queue_path=queue,
        rejection_path=tmp_path / "rejections.jsonl",
        history_path=tmp_path / "history.jsonl",
        lock_path=tmp_path / "cycle.lock",
        log_path=tmp_path / "cycle.log.jsonl",
        delay_seconds=0,
        retries=0,
        client_factory=lambda _token: client,
        clock=lambda: BASE + timedelta(minutes=5),
    )

    assert result["status"] == "finished"
    assert result["collector"]["queries"] == 17
    assert result["monitor"]["status_counts"] == {"ok": 1}
    assert client.calls[:2] == [
        "search:Donald Tusk lang:pl",
        "search:Karol Nawrocki lang:pl",
    ]
    assert client.calls[-1] == "get_tweet_info"
    log_lines = (tmp_path / "cycle.log.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["status"] for line in log_lines] == [
        "started",
        "finished",
    ]


def test_cycle_skips_when_another_process_holds_lock(tmp_path: Path) -> None:
    lock = tmp_path / "cycle.lock"
    lock.write_text(
        json.dumps({"pid": os.getpid(), "started_at": BASE.isoformat()}),
        encoding="utf-8",
    )

    result = run_cycle(
        queue_path=tmp_path / "queue.jsonl",
        rejection_path=tmp_path / "rejections.jsonl",
        history_path=tmp_path / "history.jsonl",
        lock_path=lock,
        log_path=tmp_path / "cycle.log.jsonl",
        dry_run=True,
    )

    assert result["status"] == "skipped_locked"
    assert lock.exists()


def test_cycle_dry_run_does_not_require_auth_or_network(tmp_path: Path) -> None:
    result = run_cycle(
        queue_path=tmp_path / "queue.jsonl",
        rejection_path=tmp_path / "rejections.jsonl",
        history_path=tmp_path / "history.jsonl",
        lock_path=tmp_path / "cycle.lock",
        log_path=tmp_path / "cycle.log.jsonl",
        dry_run=True,
    )

    assert result["status"] == "dry_run"
    assert result["collector"]["network"] is False
    assert not (tmp_path / "history.jsonl").exists()
