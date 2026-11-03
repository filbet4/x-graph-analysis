"""Analyze the validated 200-post domain annotation sample."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "domain_annotation_sample.csv"
OUTPUT = ROOT / "reports"

DOMAINS = ("politics", "sport", "pop_culture")
LABELS = DOMAINS + ("other", "unclear")


def main() -> None:
    with INPUT.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if len(rows) != 200:
        raise ValueError(f"Expected 200 posts, found {len(rows)}")

    ids = [row["post_id"] for row in rows]
    if any(not post_id.strip() for post_id in ids):
        raise ValueError("Empty post_id detected")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate post IDs detected")

    for number, row in enumerate(rows, 1):
        if any(row[label] not in ("0", "1") for label in LABELS):
            raise ValueError(f"Invalid labels in post {number}")

        active = [label for label in LABELS if row[label] == "1"]

        if not active:
            raise ValueError(f"No active label in post {number}")

        if len(active) > 1 and (
            "other" in active or "unclear" in active
        ):
            raise ValueError(
                f"Conflicting labels in post {number}: {active}"
            )

    counts = Counter()
    for row in rows:
        for label in LABELS:
            if row[label] == "1":
                counts[label] += 1

    multi = sum(
        sum(row[d] == "1" for d in DOMAINS) > 1
        for row in rows
    )

    lines = [
        "DOMAIN ANNOTATION SAMPLE REPORT",
        "=" * 55,
        f"Total posts: {len(rows)}",
        "Annotation completeness: 100%",
        "Validation: PASSED",
        "",
        "LABEL DISTRIBUTION",
        "-" * 55,
    ]

    for label in LABELS:
        count = counts[label]
        lines.append(
            f"{label}: {count} ({count / len(rows):.1%})"
        )

    lines.extend([
        f"Multi-label posts: {multi}",
        "",
        "SAMPLING QUALITY",
        "-" * 55,
    ])

    matrix_rows = []
    total_matches = 0

    for domain in DOMAINS:
        subset = [
            row for row in rows
            if row["sampling_stratum"] == domain
        ]

        matches = sum(row[domain] == "1" for row in subset)
        total_matches += matches
        rate = matches / len(subset) if subset else 0

        lines.append(
            f"{domain}: {matches}/{len(subset)} ({rate:.1%})"
        )

        result = {
            "sampling_stratum": domain,
            "total": len(subset),
            "matches": matches,
            "match_rate": f"{rate:.4f}",
        }

        for label in LABELS:
            result[label] = sum(
                row[label] == "1" for row in subset
            )

        matrix_rows.append(result)

    lines.extend([
        "",
        f"Overall matching posts: {total_matches}/{len(rows)}",
        f"Overall matching rate: {total_matches / len(rows):.1%}",
        "",
        "CROSS-DOMAIN MATRIX",
        "-" * 55,
    ])

    for result in matrix_rows:
        lines.append(
            f"{result['sampling_stratum']}: "
            + ", ".join(
                f"{label}={result[label]}" for label in LABELS
            )
        )

    lines.extend([
        "",
        "METHODOLOGICAL NOTES",
        "-" * 55,
        "A post may belong to more than one topical domain.",
        "The 'other' and 'unclear' labels are exclusive.",
        "Sampling match rate is not classifier accuracy.",
        "This is a stratified sample, not a random sample of all X.",
    ])

    OUTPUT.mkdir(parents=True, exist_ok=True)

    report_path = OUTPUT / "domain_annotation_report.txt"
    matrix_path = OUTPUT / "domain_sampling_matrix.csv"

    report_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    with matrix_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        fieldnames = [
            "sampling_stratum",
            "total",
            "matches",
            "match_rate",
            *LABELS,
        ]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(matrix_rows)

    print("\n".join(lines))
    print("\nFILES CREATED:")
    print(report_path)
    print(matrix_path)


if __name__ == "__main__":
    main()
