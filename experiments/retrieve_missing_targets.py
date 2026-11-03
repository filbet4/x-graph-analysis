"""Retrieve one-hop missing interaction targets from the large Scweet sample.

The script:
- loads the original large Search sample,
- identifies missing direct REPLY and QUOTE targets,
- retrieves those tweets using Scweet get_tweet_info(),
- stores retrieved targets separately,
- supports resuming after interruption or rate limits,
- never expands relationships of retrieved targets.

This is intentionally a fixed one-hop expansion.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from Scweet import Scweet


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_large_sample.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_one_hop_targets.json"
)

CHECKPOINT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_one_hop_targets_checkpoint.json"
)

# Keep batches reasonably small.
BATCH_SIZE = 50

# Small pause between successful batches.
BATCH_DELAY_SECONDS = 2


def now_iso() -> str:
    """Return current UTC timestamp."""

    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file."""

    return json.loads(
        path.read_text(encoding="utf-8")
    )


def save_json(
    path: Path,
    data: dict[str, Any],
) -> None:
    """Save JSON atomically."""

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(path)


def get_record(
    item: dict[str, Any],
) -> dict[str, Any]:
    """Return record from source item."""

    record = item.get("record", {})

    if isinstance(record, dict):
        return record

    return {}


def get_tweet_id(
    item: dict[str, Any],
) -> str | None:
    """Return normalized tweet ID."""

    tweet_id = item.get("tweet_id")

    if tweet_id is None:
        tweet_id = get_record(item).get(
            "tweet_id"
        )

    if tweet_id is None:
        return None

    return str(tweet_id)


def get_reply_target(
    record: dict[str, Any],
) -> str | None:
    """Extract direct reply target."""

    value = record.get(
        "in_reply_to_tweet_id"
    )

    if value:
        return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get(
                "in_reply_to_status_id_str"
            )

            if value:
                return str(value)

    return None


def get_quote_target(
    record: dict[str, Any],
) -> str | None:
    """Extract direct quote target."""

    quoted_tweet = record.get(
        "quoted_tweet"
    )

    if isinstance(quoted_tweet, dict):
        value = quoted_tweet.get(
            "tweet_id"
        )

        if value:
            return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get(
                "quoted_status_id_str"
            )

            if value:
                return str(value)

    return None


def find_missing_targets(
    records: list[dict[str, Any]],
) -> tuple[
    set[str],
    set[str],
    set[str],
]:
    """Find missing direct REPLY and QUOTE targets."""

    corpus_ids = {
        tweet_id
        for item in records
        if (
            tweet_id := get_tweet_id(item)
        )
        is not None
    }

    reply_targets: set[str] = set()
    quote_targets: set[str] = set()

    for item in records:
        record = get_record(item)

        reply_target = get_reply_target(
            record
        )

        if (
            reply_target
            and reply_target not in corpus_ids
        ):
            reply_targets.add(
                reply_target
            )

        quote_target = get_quote_target(
            record
        )

        if (
            quote_target
            and quote_target not in corpus_ids
        ):
            quote_targets.add(
                quote_target
            )

    all_targets = (
        reply_targets
        | quote_targets
    )

    return (
        reply_targets,
        quote_targets,
        all_targets,
    )


def create_initial_state(
    reply_targets: set[str],
    quote_targets: set[str],
    all_targets: set[str],
) -> dict[str, Any]:
    """Create initial retrieval state."""

    return {
        "metadata": {
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "source_file": SOURCE_PATH.name,
            "expansion_depth": 1,
            "recursive_expansion": False,
            "batch_size": BATCH_SIZE,
            "reply_target_count": len(
                reply_targets
            ),
            "quote_target_count": len(
                quote_targets
            ),
            "reply_quote_overlap": len(
                reply_targets
                & quote_targets
            ),
            "unique_target_count": len(
                all_targets
            ),
            "status": "running",
        },
        "requested_target_ids": sorted(
            all_targets
        ),
        "retrieved_records": [],
        "retrieved_ids": [],
        "attempted_ids": [],
        "unresolved_ids": [],
        "batches": [],
    }


def load_or_create_state(
    reply_targets: set[str],
    quote_targets: set[str],
    all_targets: set[str],
) -> dict[str, Any]:
    """Load existing state or create a new one."""

    if OUTPUT_PATH.exists():
        print(
            f"Loading existing output: "
            f"{OUTPUT_PATH}"
        )

        state = load_json(OUTPUT_PATH)

    elif CHECKPOINT_PATH.exists():
        print(
            f"Loading checkpoint: "
            f"{CHECKPOINT_PATH}"
        )

        state = load_json(
            CHECKPOINT_PATH
        )

    else:
        print(
            "Creating new one-hop "
            "retrieval dataset."
        )

        state = create_initial_state(
            reply_targets,
            quote_targets,
            all_targets,
        )

    stored_targets = set(
        str(value)
        for value in state.get(
            "requested_target_ids",
            [],
        )
    )

    if stored_targets != all_targets:
        raise RuntimeError(
            "The target set in the existing "
            "one-hop dataset differs from the "
            "current source dataset. "
            "Do not continue automatically."
        )

    return state


def normalize_result(
    result: Any,
) -> list[dict[str, Any]]:
    """Normalize Scweet get_tweet_info result."""

    if result is None:
        return []

    if isinstance(result, list):
        return [
            item
            for item in result
            if isinstance(item, dict)
        ]

    # Some Scweet versions may return
    # dataframe-like objects.
    if hasattr(result, "to_dict"):
        try:
            records = result.to_dict(
                orient="records"
            )

            if isinstance(records, list):
                return [
                    item
                    for item in records
                    if isinstance(item, dict)
                ]
        except (TypeError, ValueError):
            pass

    if isinstance(result, dict):
        # If Scweet returns a wrapper.
        for key in (
            "records",
            "tweets",
            "data",
        ):
            value = result.get(key)

            if isinstance(value, list):
                return [
                    item
                    for item in value
                    if isinstance(item, dict)
                ]

        return [result]

    return []


def get_result_tweet_id(
    record: dict[str, Any],
) -> str | None:
    """Extract tweet ID from raw Scweet get_tweet_info result."""

    # get_tweet_info(raw_json=True) returns the raw X Tweet object.
    # Its primary tweet identifier is stored in top-level rest_id.
    value = record.get("rest_id")

    if value:
        return str(value)

    # Fallback to legacy.id_str.
    legacy = record.get("legacy")

    if isinstance(legacy, dict):
        value = legacy.get("id_str")

        if value:
            return str(value)

    # Additional defensive fallbacks.
    for key in (
        "tweet_id",
        "id",
        "id_str",
    ):
        value = record.get(key)

        if value:
            return str(value)

    return None


def persist_state(
    state: dict[str, Any],
) -> None:
    """Persist output and checkpoint."""

    state["metadata"]["updated_at"] = (
        now_iso()
    )

    save_json(
        OUTPUT_PATH,
        state,
    )

    save_json(
        CHECKPOINT_PATH,
        state,
    )


def main() -> None:
    """Retrieve direct missing targets."""

    if not SOURCE_PATH.exists():
        raise FileNotFoundError(
            f"Source dataset not found: "
            f"{SOURCE_PATH}"
        )

    token = os.environ.get(
        "SCWEET_AUTH_TOKEN"
    )

    if not token:
        raise RuntimeError(
            "SCWEET_AUTH_TOKEN is not set."
        )

    source_data = load_json(
        SOURCE_PATH
    )

    records = source_data.get(
        "records",
        []
    )

    if not isinstance(records, list):
        raise ValueError(
            "Source field 'records' "
            "must be a list."
        )

    (
        reply_targets,
        quote_targets,
        all_targets,
    ) = find_missing_targets(records)

    print("=" * 70)
    print("ONE-HOP TARGET RETRIEVAL")
    print("=" * 70)

    print(
        f"Source posts:          "
        f"{len(records)}"
    )

    print(
        f"Missing REPLY targets: "
        f"{len(reply_targets)}"
    )

    print(
        f"Missing QUOTE targets: "
        f"{len(quote_targets)}"
    )

    print(
        f"REPLY/QUOTE overlap:   "
        f"{len(reply_targets & quote_targets)}"
    )

    print(
        f"Unique targets:        "
        f"{len(all_targets)}"
    )

    state = load_or_create_state(
        reply_targets,
        quote_targets,
        all_targets,
    )

    retrieved_ids = {
        str(value)
        for value in state.get(
            "retrieved_ids",
            []
        )
    }

    attempted_ids = {
        str(value)
        for value in state.get(
            "attempted_ids",
            []
        )
    }

    # IDs successfully retrieved earlier
    # are always skipped.
    #
    # IDs attempted but not returned are also
    # skipped within this fixed retrieval run.
    completed_ids = (
        retrieved_ids
        | attempted_ids
    )

    pending_ids = sorted(
        all_targets
        - completed_ids
    )

    print()
    print(
        f"Already retrieved:     "
        f"{len(retrieved_ids)}"
    )

    print(
        f"Already attempted:     "
        f"{len(attempted_ids)}"
    )

    print(
        f"Pending:               "
        f"{len(pending_ids)}"
    )

    if not pending_ids:
        state["metadata"]["status"] = (
            "finished"
        )

        unresolved = (
            all_targets
            - retrieved_ids
        )

        state["unresolved_ids"] = sorted(
            unresolved
        )

        persist_state(state)

        print()
        print(
            "No pending targets."
        )

        print(
            f"Retrieved:  "
            f"{len(retrieved_ids)}"
        )

        print(
            f"Unresolved: "
            f"{len(unresolved)}"
        )

        return

    # Use the same Scweet authentication
    # mechanism as the collection scripts.
    scweet = Scweet(
        auth_token=token
    )

    total_batches = (
        len(pending_ids)
        + BATCH_SIZE
        - 1
    ) // BATCH_SIZE

    stop_due_to_error = False

    for batch_number, start in enumerate(
        range(
            0,
            len(pending_ids),
            BATCH_SIZE,
        ),
        start=1,
    ):
        batch_ids = pending_ids[
            start:start + BATCH_SIZE
        ]

        print()
        print("=" * 70)

        print(
            f"BATCH {batch_number}/"
            f"{total_batches}"
        )

        print("=" * 70)

        print(
            f"Requested IDs: "
            f"{len(batch_ids)}"
        )

        batch_info: dict[str, Any] = {
            "started_at": now_iso(),
            "requested_ids": batch_ids,
            "status": "running",
            "retrieved_ids": [],
            "unresolved_ids": [],
        }

        try:
            result = scweet.get_tweet_info(
                tweet_ids=batch_ids,
                raw_json=True,
                save=False,
            )

            returned_records = (
                normalize_result(result)
            )

            batch_retrieved_ids: set[str] = (
                set()
            )

            new_records = 0

            for record in returned_records:
                tweet_id = (
                    get_result_tweet_id(
                        record
                    )
                )

                if tweet_id is None:
                    continue

                # Only accept records that
                # belong to this requested batch.
                if tweet_id not in batch_ids:
                    continue

                batch_retrieved_ids.add(
                    tweet_id
                )

                if tweet_id in retrieved_ids:
                    continue

                state[
                    "retrieved_records"
                ].append(record)

                retrieved_ids.add(
                    tweet_id
                )

                new_records += 1

            attempted_ids.update(
                batch_ids
            )

            batch_unresolved = (
                set(batch_ids)
                - batch_retrieved_ids
            )

            batch_info["status"] = "ok"

            batch_info[
                "retrieved_ids"
            ] = sorted(
                batch_retrieved_ids
            )

            batch_info[
                "unresolved_ids"
            ] = sorted(
                batch_unresolved
            )

            batch_info[
                "finished_at"
            ] = now_iso()

            batch_info[
                "returned_records"
            ] = len(returned_records)

            batch_info[
                "new_records"
            ] = new_records

            state["batches"].append(
                batch_info
            )

            state["retrieved_ids"] = (
                sorted(retrieved_ids)
            )

            state["attempted_ids"] = (
                sorted(attempted_ids)
            )

            state["unresolved_ids"] = (
                sorted(
                    attempted_ids
                    - retrieved_ids
                )
            )

            persist_state(state)

            print(
                f"Returned records: "
                f"{len(returned_records)}"
            )

            print(
                f"Retrieved requested IDs: "
                f"{len(batch_retrieved_ids)}"
            )

            print(
                f"Unresolved in batch: "
                f"{len(batch_unresolved)}"
            )

            print(
                f"Total retrieved: "
                f"{len(retrieved_ids)}"
            )

            if (
                start + BATCH_SIZE
                < len(pending_ids)
            ):
                time.sleep(
                    BATCH_DELAY_SECONDS
                )

        except Exception as exc:
            batch_info["status"] = "error"

            batch_info["error"] = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            batch_info[
                "finished_at"
            ] = now_iso()

            state["batches"].append(
                batch_info
            )

            # IMPORTANT:
            # Failed batch IDs are NOT marked
            # as attempted, so the next run
            # will retry them.
            state["retrieved_ids"] = (
                sorted(retrieved_ids)
            )

            state["attempted_ids"] = (
                sorted(attempted_ids)
            )

            state["unresolved_ids"] = (
                sorted(
                    attempted_ids
                    - retrieved_ids
                )
            )

            state["metadata"]["status"] = (
                "partial"
            )

            persist_state(state)

            print(
                "Batch failed:"
            )

            print(
                f"  {type(exc).__name__}: "
                f"{exc}"
            )

            print()
            print(
                "Stopping safely. "
                "Run the script again later "
                "to resume."
            )

            stop_due_to_error = True
            break

    unresolved_ids = (
        attempted_ids
        - retrieved_ids
    )

    pending_after_run = (
        all_targets
        - attempted_ids
        - retrieved_ids
    )

    if (
        not stop_due_to_error
        and not pending_after_run
    ):
        state["metadata"]["status"] = (
            "finished"
        )
    else:
        state["metadata"]["status"] = (
            "partial"
        )

    state["retrieved_ids"] = sorted(
        retrieved_ids
    )

    state["attempted_ids"] = sorted(
        attempted_ids
    )

    state["unresolved_ids"] = sorted(
        unresolved_ids
    )

    persist_state(state)

    print()
    print("=" * 70)
    print("RETRIEVAL RUN FINISHED")
    print("=" * 70)

    print(
        f"Requested targets: "
        f"{len(all_targets)}"
    )

    print(
        f"Retrieved targets: "
        f"{len(retrieved_ids)}"
    )

    print(
        f"Attempted but unresolved: "
        f"{len(unresolved_ids)}"
    )

    print(
        f"Not attempted yet: "
        f"{len(pending_after_run)}"
    )

    print(
        "Status: "
        f"{state['metadata']['status']}"
    )

    print()
    print(
        f"Dataset:    {OUTPUT_PATH}"
    )

    print(
        f"Checkpoint: {CHECKPOINT_PATH}"
    )


if __name__ == "__main__":
    main()