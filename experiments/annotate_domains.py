"""Interactive manual annotation using safe mixed-stratum batches."""

from __future__ import annotations

import argparse
from pathlib import Path

from annotation_workflow import (
    LABEL_COLUMNS,
    SAMPLING_STRATA,
    AnnotationFileError,
    apply_labels,
    is_annotated,
    load_rows,
    progress,
    save_rows_atomic,
    select_batch,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = PROJECT_ROOT / "data" / "domain_annotation_sample.csv"
LABELS = {
    "1": "politics",
    "2": "sport",
    "3": "pop_culture",
    "4": "other",
    "5": "unclear",
}


def parse_args() -> argparse.Namespace:
    """Parse batch and stratum selection options."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Maximum number of unannotated posts to present (default: 20)",
    )
    parser.add_argument(
        "--strata",
        nargs="+",
        choices=SAMPLING_STRATA,
        default=list(SAMPLING_STRATA),
        help="Sampling strata to mix in round-robin order",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_PATH,
        help="Annotation CSV path",
    )
    return parser.parse_args()


def parse_selection(answer: str) -> set[str] | None:
    """Parse explicit numeric or label-name choices, or return None for control input."""
    choices = {part.strip().lower() for part in answer.split(",") if part.strip()}
    name_to_number = {name: number for number, name in LABELS.items()}
    choices = {name_to_number.get(choice, choice) for choice in choices}
    if not choices or not choices.issubset(LABELS):
        raise AnnotationFileError("Use 1-5 or label names, for example 1,2")
    selected = {LABELS[choice] for choice in choices}
    if "other" in selected and len(selected) > 1:
        raise AnnotationFileError("other must be selected alone")
    if "unclear" in selected and len(selected) > 1:
        raise AnnotationFileError("unclear must be selected alone")
    return selected


def print_progress(rows: list[dict[str, str]]) -> None:
    """Print overall and stratum progress."""
    status = progress(rows)
    print(f"Completed: {status.annotated}/{status.total}")
    for stratum, (annotated, unannotated) in status.by_stratum.items():
        print(f"  {stratum}: {annotated} annotated, {unannotated} remaining")


def main() -> None:
    """Annotate one safe, mixed-stratum batch without inferring labels."""
    args = parse_args()
    rows, fieldnames = load_rows(args.csv)
    indexes = select_batch(rows, args.batch_size, strata=args.strata)
    backup_path: Path | None = None

    print("\nDOMAIN ANNOTATION BATCH")
    print("1 = POLITICS | 2 = SPORT | 3 = POP_CULTURE")
    print("4 = OTHER   | 5 = UNCLEAR")
    print("Multiple labels: e.g. 1,2")
    print("s = skip | q = quit")
    print_progress(rows)
    print(f"Selected batch: {len(indexes)} posts")
    print("-" * 70)

    for position, row_index in enumerate(indexes, start=1):
        row = rows[row_index]
        print(f"\nBATCH POST {position}/{len(indexes)}")
        print(f"CSV row: {row_index + 2}")
        print(f"ID: {row['post_id']}")
        print(f"Stratum: {row['sampling_stratum']} | Batch: {row['batch']}")
        print("-" * 70)
        print(row["text"])
        print("-" * 70)

        while True:
            try:
                answer = input("Choose label(s): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nProgress is saved after every accepted annotation. Exiting.")
                return

            if answer == "q":
                print("Progress is saved after every accepted annotation. Exiting.")
                return
            if answer == "s":
                break

            try:
                selected = parse_selection(answer)
                if selected is None:
                    continue
                apply_labels(row, selected)
                backup_path = save_rows_atomic(
                    args.csv,
                    rows,
                    fieldnames,
                    backup_path=backup_path,
                )
            except AnnotationFileError as error:
                print(f"Invalid annotation: {error}")
                continue

            print(f"Saved: {', '.join(sorted(selected))}")
            break

    print("\nBatch complete.")
    print_progress(rows)
    if backup_path:
        print(f"Backup: {backup_path}")


if __name__ == "__main__":
    main()
