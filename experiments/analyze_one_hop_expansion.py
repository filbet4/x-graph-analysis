"""Compare graph completeness before and after fixed one-hop expansion.

Important methodological rule:
- original Search posts are the seed population,
- retrieved one-hop tweets are structural context only,
- relationships are extracted ONLY from seed posts,
- relationships originating from one-hop targets are ignored,
- no recursive expansion is performed.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import networkx as nx


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_large_sample.json"
)

TARGETS_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_one_hop_targets.json"
)


def load_json(path: Path) -> dict[str, Any]:
    """Load JSON file."""

    return json.loads(
        path.read_text(encoding="utf-8")
    )


# ----------------------------------------------------------------------
# Seed record helpers
# ----------------------------------------------------------------------


def get_seed_record(
    item: dict[str, Any],
) -> dict[str, Any]:
    """Return normalized record from Search dataset."""

    record = item.get("record", {})

    if isinstance(record, dict):
        return record

    return {}


def get_seed_tweet_id(
    item: dict[str, Any],
) -> str | None:
    """Extract tweet ID from Search dataset item."""

    value = item.get("tweet_id")

    if value is None:
        value = get_seed_record(item).get(
            "tweet_id"
        )

    if value is None:
        return None

    return str(value)


def get_reply_target(
    record: dict[str, Any],
) -> str | None:
    """Extract direct reply target from seed record."""

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
    """Extract direct quote target from seed record."""

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


# ----------------------------------------------------------------------
# One-hop target helpers
# ----------------------------------------------------------------------


def get_target_tweet_id(
    record: dict[str, Any],
) -> str | None:
    """Extract ID from raw get_tweet_info result."""

    value = record.get("rest_id")

    if value:
        return str(value)

    legacy = record.get("legacy")

    if isinstance(legacy, dict):
        value = legacy.get("id_str")

        if value:
            return str(value)

    for key in (
        "tweet_id",
        "id",
        "id_str",
    ):
        value = record.get(key)

        if value:
            return str(value)

    return None


# ----------------------------------------------------------------------
# Relationship extraction
# ----------------------------------------------------------------------


def extract_relationships(
    seed_records: list[dict[str, Any]],
) -> dict[str, list[tuple[str, str]]]:
    """Extract relationships originating from seed posts only."""

    relationships: dict[
        str,
        list[tuple[str, str]],
    ] = {
        "REPLY": [],
        "QUOTE": [],
    }

    for item in seed_records:
        source_id = get_seed_tweet_id(item)

        if source_id is None:
            continue

        record = get_seed_record(item)

        reply_target = get_reply_target(
            record
        )

        if reply_target:
            relationships["REPLY"].append(
                (
                    source_id,
                    reply_target,
                )
            )

        quote_target = get_quote_target(
            record
        )

        if quote_target:
            relationships["QUOTE"].append(
                (
                    source_id,
                    quote_target,
                )
            )

    return relationships


# ----------------------------------------------------------------------
# Graph analysis
# ----------------------------------------------------------------------


def build_internal_graph(
    relationships: list[tuple[str, str]],
    available_ids: set[str],
) -> nx.DiGraph:
    """Build directed graph from relationships with available endpoints."""

    graph = nx.DiGraph()

    for source_id, target_id in relationships:
        if (
            source_id in available_ids
            and target_id in available_ids
        ):
            graph.add_edge(
                source_id,
                target_id,
            )

    return graph


def graph_statistics(
    graph: nx.DiGraph,
) -> dict[str, int | float]:
    """Calculate basic structural graph statistics."""

    nodes = graph.number_of_nodes()
    edges = graph.number_of_edges()

    if nodes > 1:
        density = nx.density(graph)

        weak_components = list(
            nx.weakly_connected_components(
                graph
            )
        )

        strong_components = list(
            nx.strongly_connected_components(
                graph
            )
        )

    elif nodes == 1:
        density = 0.0
        weak_components = [
            set(graph.nodes())
        ]
        strong_components = [
            set(graph.nodes())
        ]

    else:
        density = 0.0
        weak_components = []
        strong_components = []

    largest_weak = max(
        (
            len(component)
            for component in weak_components
        ),
        default=0,
    )

    max_in_degree = max(
        (
            degree
            for _, degree
            in graph.in_degree()
        ),
        default=0,
    )

    max_out_degree = max(
        (
            degree
            for _, degree
            in graph.out_degree()
        ),
        default=0,
    )

    return {
        "nodes": nodes,
        "edges": edges,
        "density": density,
        "weak_components": len(
            weak_components
        ),
        "strong_components": len(
            strong_components
        ),
        "largest_weak_component": (
            largest_weak
        ),
        "max_in_degree": max_in_degree,
        "max_out_degree": max_out_degree,
    }


def print_graph_statistics(
    name: str,
    stats: dict[str, int | float],
) -> None:
    """Print graph statistics."""

    print(name)
    print("-" * 70)

    print(
        f"Nodes participating:      "
        f"{stats['nodes']}"
    )

    print(
        f"Edges:                    "
        f"{stats['edges']}"
    )

    print(
        f"Density:                  "
        f"{stats['density']:.8f}"
    )

    print(
        f"Weak components:          "
        f"{stats['weak_components']}"
    )

    print(
        f"Strong components:        "
        f"{stats['strong_components']}"
    )

    print(
        f"Largest weak component:   "
        f"{stats['largest_weak_component']}"
    )

    print(
        f"Maximum in-degree:         "
        f"{stats['max_in_degree']}"
    )

    print(
        f"Maximum out-degree:        "
        f"{stats['max_out_degree']}"
    )


def print_comparison(
    relationship_type: str,
    relationships: list[tuple[str, str]],
    before_ids: set[str],
    after_ids: set[str],
) -> None:
    """Compare relationship completeness and graph structure."""

    total = len(relationships)

    before_internal = [
        edge
        for edge in relationships
        if edge[1] in before_ids
    ]

    after_internal = [
        edge
        for edge in relationships
        if edge[1] in after_ids
    ]

    before_missing = {
        target_id
        for _, target_id in relationships
        if target_id not in before_ids
    }

    after_missing = {
        target_id
        for _, target_id in relationships
        if target_id not in after_ids
    }

    before_completeness = (
        len(before_internal)
        / total
        * 100
        if total
        else 0.0
    )

    after_completeness = (
        len(after_internal)
        / total
        * 100
        if total
        else 0.0
    )

    print()
    print("=" * 70)
    print(
        f"{relationship_type}: "
        "BEFORE VS AFTER ONE-HOP"
    )
    print("=" * 70)

    print(
        f"Total seed relationships: "
        f"{total}"
    )

    print()
    print("BEFORE")
    print("-" * 70)

    print(
        f"Internal relationships:   "
        f"{len(before_internal)}"
    )

    print(
        f"Unique missing targets:   "
        f"{len(before_missing)}"
    )

    print(
        f"Completeness:              "
        f"{before_completeness:.2f}%"
    )

    print()
    print("AFTER")
    print("-" * 70)

    print(
        f"Internal relationships:   "
        f"{len(after_internal)}"
    )

    print(
        f"Unique missing targets:   "
        f"{len(after_missing)}"
    )

    print(
        f"Completeness:              "
        f"{after_completeness:.2f}%"
    )

    print()
    print(
        f"Recovered relationships:  "
        f"{len(after_internal) - len(before_internal)}"
    )

    print(
        f"Completeness gain:         "
        f"{after_completeness - before_completeness:.2f} pp"
    )

    before_graph = build_internal_graph(
        relationships,
        before_ids,
    )

    after_graph = build_internal_graph(
        relationships,
        after_ids,
    )

    print()
    print_graph_statistics(
        "GRAPH BEFORE",
        graph_statistics(before_graph),
    )

    print()
    print_graph_statistics(
        "GRAPH AFTER",
        graph_statistics(after_graph),
    )


def main() -> None:
    """Run before/after one-hop analysis."""

    if not SOURCE_PATH.exists():
        raise FileNotFoundError(
            f"Source dataset not found: "
            f"{SOURCE_PATH}"
        )

    if not TARGETS_PATH.exists():
        raise FileNotFoundError(
            f"One-hop dataset not found: "
            f"{TARGETS_PATH}"
        )

    source_data = load_json(
        SOURCE_PATH
    )

    target_data = load_json(
        TARGETS_PATH
    )

    seed_records = source_data.get(
        "records",
        [],
    )

    target_records = target_data.get(
        "retrieved_records",
        [],
    )

    if not isinstance(seed_records, list):
        raise ValueError(
            "Source records must be a list."
        )

    if not isinstance(target_records, list):
        raise ValueError(
            "Retrieved target records "
            "must be a list."
        )

    seed_ids = {
        tweet_id
        for item in seed_records
        if (
            tweet_id := get_seed_tweet_id(
                item
            )
        )
    }

    target_ids = {
        tweet_id
        for record in target_records
        if (
            tweet_id := get_target_tweet_id(
                record
            )
        )
    }

    overlap = (
        seed_ids
        & target_ids
    )

    expanded_ids = (
        seed_ids
        | target_ids
    )

    relationships = (
        extract_relationships(
            seed_records
        )
    )

    print("=" * 70)
    print(
        "ONE-HOP EXPANSION ANALYSIS"
    )
    print("=" * 70)

    print(
        f"Original seed posts:       "
        f"{len(seed_ids)}"
    )

    print(
        f"Retrieved target posts:    "
        f"{len(target_ids)}"
    )

    print(
        f"Seed/target overlap:       "
        f"{len(overlap)}"
    )

    print(
        f"Expanded available posts:  "
        f"{len(expanded_ids)}"
    )

    print()
    print(
        "IMPORTANT: relationships are "
        "extracted only from original "
        "Search seed posts."
    )

    # --------------------------------------------------------------
    # Retrieval status
    # --------------------------------------------------------------

    requested_ids = {
        str(value)
        for value in target_data.get(
            "requested_target_ids",
            [],
        )
    }

    unresolved_ids = {
        str(value)
        for value in target_data.get(
            "unresolved_ids",
            [],
        )
    }

    print()
    print("=" * 70)
    print("ONE-HOP RETRIEVAL")
    print("=" * 70)

    print(
        f"Requested unique targets:  "
        f"{len(requested_ids)}"
    )

    print(
        f"Retrieved unique targets:  "
        f"{len(target_ids)}"
    )

    print(
        f"Unresolved unique targets: "
        f"{len(unresolved_ids)}"
    )

    retrieval_rate = (
        len(target_ids)
        / len(requested_ids)
        * 100
        if requested_ids
        else 0.0
    )

    print(
        f"Retrieval success rate:    "
        f"{retrieval_rate:.2f}%"
    )

    # --------------------------------------------------------------
    # Which relationship types are represented by unresolved IDs?
    # --------------------------------------------------------------

    unresolved_by_type: Counter[str] = (
        Counter()
    )

    for relationship_type, edges in (
        relationships.items()
    ):
        unresolved_for_type = {
            target_id
            for _, target_id in edges
            if target_id in unresolved_ids
        }

        unresolved_by_type[
            relationship_type
        ] = len(
            unresolved_for_type
        )

    print()
    print(
        "Unresolved unique targets "
        "by relationship type:"
    )

    print(
        f"  REPLY: "
        f"{unresolved_by_type['REPLY']}"
    )

    print(
        f"  QUOTE: "
        f"{unresolved_by_type['QUOTE']}"
    )

    # --------------------------------------------------------------
    # Before vs after
    # --------------------------------------------------------------

    print_comparison(
        "REPLY",
        relationships["REPLY"],
        seed_ids,
        expanded_ids,
    )

    print_comparison(
        "QUOTE",
        relationships["QUOTE"],
        seed_ids,
        expanded_ids,
    )

    # --------------------------------------------------------------
    # Combined interaction graph
    #
    # This is diagnostic only. Separate relationship graphs remain
    # the primary analysis.
    # --------------------------------------------------------------

    combined_relationships = (
        relationships["REPLY"]
        + relationships["QUOTE"]
    )

    print()
    print("=" * 70)
    print(
        "COMBINED REPLY + QUOTE "
        "DIAGNOSTIC"
    )
    print("=" * 70)

    combined_before = (
        build_internal_graph(
            combined_relationships,
            seed_ids,
        )
    )

    combined_after = (
        build_internal_graph(
            combined_relationships,
            expanded_ids,
        )
    )

    print()
    print_graph_statistics(
        "COMBINED GRAPH BEFORE",
        graph_statistics(
            combined_before
        ),
    )

    print()
    print_graph_statistics(
        "COMBINED GRAPH AFTER",
        graph_statistics(
            combined_after
        ),
    )

    print()
    print("=" * 70)
    print("ANALYSIS FINISHED")
    print("=" * 70)


if __name__ == "__main__":
    main()