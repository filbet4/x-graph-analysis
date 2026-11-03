"""Analyze the manually annotated multidomain sample."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "multidomain_annotation_sample_annotated.csv"
)


def is_positive(value: str) -> bool:
    return value.strip() == "1"


def get_actual_domains(row: dict[str, str]) -> set[str]:
    domains = set()

    if is_positive(row["politics"]):
        domains.add("politics")

    if is_positive(row["sport"]):
        domains.add("sport")

    if is_positive(row["pop_culture"]):
        domains.add("pop_culture")

    return domains


def main() -> None:
    with INPUT_PATH.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        rows = list(csv.DictReader(file))

    print("=== ANNOTATION SAMPLE ANALYSIS ===")
    print(f"Total posts: {len(rows)}")

    # Language distribution
    languages = Counter(
        row["language"].strip().lower()
        for row in rows
    )

    print("\nLanguages:")

    for language, count in languages.most_common():
        percentage = count / len(rows) * 100
        print(
            f"  {language or 'missing'}: "
            f"{count} ({percentage:.1f}%)"
        )

    # Actual domain distribution
    domain_counts = Counter()

    for row in rows:
        domains = get_actual_domains(row)

        for domain in domains:
            domain_counts[domain] += 1

        if is_positive(row["other"]):
            domain_counts["other"] += 1

    print("\nActual content domains:")

    for domain in (
        "politics",
        "sport",
        "pop_culture",
        "other",
    ):
        count = domain_counts[domain]
        percentage = count / len(rows) * 100

        print(
            f"  {domain}: "
            f"{count} ({percentage:.1f}%)"
        )

    # Sampling-domain precision
    print("\nSampling-domain precision:")

    sampling_domains = (
        "politics",
        "sport",
        "pop_culture",
    )

    for sampling_domain in sampling_domains:
        subset = [
            row
            for row in rows
            if row["sampling_domain"] == sampling_domain
        ]

        correct = sum(
            sampling_domain in get_actual_domains(row)
            for row in subset
        )

        precision = (
            correct / len(subset) * 100
            if subset
            else 0
        )

        print(
            f"  {sampling_domain}: "
            f"{correct}/{len(subset)} "
            f"({precision:.1f}%)"
        )

    # Polish-only precision
    print("\nSampling-domain precision (Polish only):")

    for sampling_domain in sampling_domains:
        subset = [
            row
            for row in rows
            if (
                row["sampling_domain"] == sampling_domain
                and row["language"].strip().lower() == "pl"
            )
        ]

        correct = sum(
            sampling_domain in get_actual_domains(row)
            for row in subset
        )

        precision = (
            correct / len(subset) * 100
            if subset
            else 0
        )

        print(
            f"  {sampling_domain}: "
            f"{correct}/{len(subset)} "
            f"({precision:.1f}%)"
        )

    # Multi-label posts
    multilabel_rows = [
        row
        for row in rows
        if len(get_actual_domains(row)) > 1
    ]

    print(
        "\nMulti-label posts: "
        f"{len(multilabel_rows)}"
    )

    # Other
    other_rows = [
        row
        for row in rows
        if is_positive(row["other"])
    ]

    print(
        "OTHER posts: "
        f"{len(other_rows)} "
        f"({len(other_rows) / len(rows) * 100:.1f}%)"
    )

    # Non-Polish
    non_polish = [
        row
        for row in rows
        if row["language"].strip().lower() != "pl"
    ]

    print(
        "Non-Polish / unknown posts: "
        f"{len(non_polish)} "
        f"({len(non_polish) / len(rows) * 100:.1f}%)"
    )

    # Potential usable posts
    usable = [
        row
        for row in rows
        if (
            row["language"].strip().lower() == "pl"
            and not is_positive(row["other"])
            and len(get_actual_domains(row)) > 0
        )
    ]

    print(
        "\nPotentially usable Polish domain posts: "
        f"{len(usable)}/{len(rows)} "
        f"({len(usable) / len(rows) * 100:.1f}%)"
    )


if __name__ == "__main__":
    main()