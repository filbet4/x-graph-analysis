"""Reusable, validated workflow for manual domain annotation batches.

This module performs only annotation-file management and progress reporting. It
never infers labels or modifies rows without an explicit caller-supplied label.
"""

from __future__ import annotations

import csv
import os
import shutil
import tempfile
from collections import Counter, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

LABEL_COLUMNS: Final[tuple[str, ...]] = (
    "politics",
    "sport",
    "pop_culture",
    "other",
    "unclear",
)
SAMPLING_STRATA: Final[tuple[str, ...]] = (
    "politics",
    "sport",
    "pop_culture",
)
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    "post_id",
    "batch",
    "sampling_stratum",
    "sampling_domains",
    "sampling_queries",
    "text",
    *LABEL_COLUMNS,
    "annotation_notes",
)
VALID_LABEL_VALUES: Final[frozenset[str]] = frozenset({"", "0", "1"})


class AnnotationFileError(ValueError):
    """Raised when an annotation CSV violates its expected structure."""


@dataclass(frozen=True, slots=True)
class AnnotationProgress:
    """Aggregated annotation progress for a CSV file."""

    total: int
    annotated: int
    unannotated: int
    by_stratum: dict[str, tuple[int, int]]
    by_batch: dict[str, tuple[int, int]]


def load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Load and validate annotation rows while preserving the CSV header."""
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]

    validate_fieldnames(fieldnames)
    validate_rows(rows, fieldnames)
    return rows, fieldnames


def validate_fieldnames(fieldnames: Sequence[str]) -> None:
    """Require all known columns without rejecting additional preserved columns."""
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        raise AnnotationFileError(
            f"Missing required annotation columns: {', '.join(missing)}"
        )
    if len(set(fieldnames)) != len(fieldnames):
        raise AnnotationFileError("Annotation CSV contains duplicate column names")


def validate_rows(rows: Sequence[dict[str, str]], fieldnames: Sequence[str]) -> None:
    """Validate row shape, label values, and multilabel exclusivity rules."""
    for index, row in enumerate(rows, start=2):
        if set(row) - set(fieldnames):
            raise AnnotationFileError(f"Row {index} contains unknown columns")
        if not row.get("post_id", "").strip():
            raise AnnotationFileError(f"Row {index} has an empty post_id")
        for label in LABEL_COLUMNS:
            value = row.get(label, "")
            if value not in VALID_LABEL_VALUES:
                raise AnnotationFileError(
                    f"Row {index} has invalid {label} value {value!r}; use '', '0', or '1'"
                )
        values = {label for label in LABEL_COLUMNS if row.get(label) == "1"}
        filled = [row.get(label, "") for label in LABEL_COLUMNS if row.get(label)]
        if filled and len(filled) != len(LABEL_COLUMNS):
            raise AnnotationFileError(f"Row {index} has partially filled labels")
        if "other" in values and len(values) > 1:
            raise AnnotationFileError(f"Row {index} combines other with another label")
        if "unclear" in values and len(values) > 1:
            raise AnnotationFileError(
                f"Row {index} combines unclear with another label"
            )


def is_annotated(row: dict[str, str]) -> bool:
    """Return whether every label column has an explicit binary value."""
    return all(row.get(label, "") in {"0", "1"} for label in LABEL_COLUMNS)


def apply_labels(row: dict[str, str], selected: Iterable[str]) -> None:
    """Apply explicitly approved labels to one row after validating the choice."""
    selected_labels = set(selected)
    if not selected_labels or not selected_labels.issubset(LABEL_COLUMNS):
        raise AnnotationFileError("Selected labels must be known and non-empty")
    if "other" in selected_labels and len(selected_labels) > 1:
        raise AnnotationFileError("other must be selected alone")
    if "unclear" in selected_labels and len(selected_labels) > 1:
        raise AnnotationFileError("unclear must be selected alone")
    for label in LABEL_COLUMNS:
        row[label] = "1" if label in selected_labels else "0"


def create_backup(path: Path) -> Path:
    """Create a timestamped backup without overwriting an earlier backup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.stem}_backup_{timestamp}{path.suffix}")
    counter = 1
    while backup.exists():
        backup = path.with_name(
            f"{path.stem}_backup_{timestamp}_{counter}{path.suffix}"
        )
        counter += 1
    shutil.copy2(path, backup)
    return backup


def save_rows_atomic(
    path: Path,
    rows: Sequence[dict[str, str]],
    fieldnames: Sequence[str],
    *,
    backup_path: Path | None = None,
) -> Path | None:
    """Validate and atomically replace a CSV, optionally creating one backup.

    The temporary file is created in the destination directory, flushed and
    synced, then installed with ``os.replace``. This avoids partial destination
    files and avoids reusing a fixed temporary filename.
    """
    validate_fieldnames(fieldnames)
    validate_rows(rows, fieldnames)
    if backup_path is None and path.exists():
        backup_path = create_backup(path)

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_name = file.name
            writer = csv.DictWriter(
                file,
                fieldnames=list(fieldnames),
                extrasaction="raise",
            )
            writer.writeheader()
            writer.writerows(rows)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_name, path)
    except Exception:
        if temporary_name:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return backup_path


def select_batch(
    rows: Sequence[dict[str, str]],
    batch_size: int,
    *,
    strata: Sequence[str] = SAMPLING_STRATA,
) -> list[int]:
    """Select unannotated row indexes in deterministic round-robin strata order."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    requested = tuple(dict.fromkeys(strata))
    if not requested:
        raise ValueError("at least one sampling stratum is required")
    queues: dict[str, deque[int]] = {
        stratum: deque(
            index
            for index, row in enumerate(rows)
            if row.get("sampling_stratum") == stratum and not is_annotated(row)
        )
        for stratum in requested
    }
    selected: list[int] = []
    while len(selected) < batch_size and any(queues.values()):
        for stratum in requested:
            if queues[stratum] and len(selected) < batch_size:
                selected.append(queues[stratum].popleft())
    return selected


def progress(rows: Sequence[dict[str, str]]) -> AnnotationProgress:
    """Calculate total, stratum, and batch annotation progress."""
    by_stratum: dict[str, tuple[int, int]] = {}
    for stratum, group in _group_rows(rows, "sampling_stratum"):
        annotated = sum(is_annotated(row) for row in group)
        by_stratum[stratum] = (annotated, len(group) - annotated)
    by_batch: dict[str, tuple[int, int]] = {}
    for batch, group in _group_rows(rows, "batch"):
        annotated = sum(is_annotated(row) for row in group)
        by_batch[batch] = (annotated, len(group) - annotated)
    annotated = sum(is_annotated(row) for row in rows)
    return AnnotationProgress(
        total=len(rows),
        annotated=annotated,
        unannotated=len(rows) - annotated,
        by_stratum=by_stratum,
        by_batch=by_batch,
    )


def _group_rows(
    rows: Sequence[dict[str, str]],
    column: str,
) -> list[tuple[str, list[dict[str, str]]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(row.get(column, ""), []).append(row)
    return list(grouped.items())
