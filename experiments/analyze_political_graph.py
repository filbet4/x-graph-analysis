
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import networkx as nx


def get_tweet_id(item):
    record = item.get("record") or {}
    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    return str(
        item.get("tweet_id")
        or record.get("tweet_id")
        or legacy.get("id_str")
        or ""
    )


def get_author(item):
    record = item.get("record") or {}
    raw = record.get("raw") or {}

    result = (
        ((raw.get("core") or {}).get("user_results") or {})
        .get("result") or {}
    )

    core = result.get("core") or {}
    user = record.get("user") or {}

    return (
        core.get("screen_name")
        or user.get("screen_name")
        or "unknown"
    )


def get_targets(item):
    record = item.get("record") or {}
    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    targets = []

    reply = legacy.get("in_reply_to_status_id_str")
    quote = legacy.get("quoted_status_id_str")

    if reply:
        targets.append(("REPLY", str(reply)))

    if quote:
        targets.append(("QUOTE", str(quote)))

    return targets


def is_political(item):
    return any(
        source.get("domain") == "politics"
        for source in item.get("sampling_sources", [])
        if isinstance(source, dict)
    )


def load_annotations(path):
    annotations = {}

    with path.open(
        encoding="utf-8-sig", newline=""
    ) as file:
        for row in csv.DictReader(file):
            tweet_id = str(row.get("tweet_id") or "").strip()

            if not tweet_id:
                continue

            annotations[tweet_id] = row

    return annotations


def analyze(source, annotations_path, output):
    payload = json.loads(
        source.read_text(encoding="utf-8")
    )

    records = payload["records"]

    political = {
        get_tweet_id(item): item
        for item in records
        if is_political(item) and get_tweet_id(item)
    }

    annotations = load_annotations(annotations_path)

    missing = set(annotations) - set(political)

    if missing:
        print(
            "UWAGA: Nie znaleziono postow z CSV:",
            len(missing),
        )

    graph = nx.MultiDiGraph()

    for tweet_id, item in political.items():
        graph.add_node(
            tweet_id,
            author=get_author(item),
            flagged=tweet_id in annotations,
            label=(
                annotations[tweet_id].get("manual_label", "")
                if tweet_id in annotations else ""
            ),
        )

    for tweet_id, item in political.items():
        for relation, target in get_targets(item):
            if target in political:
                graph.add_edge(
                    tweet_id,
                    target,
                    relation=relation,
                )

    flagged_ids = set(annotations) & set(political)

    flagged_graph = graph.subgraph(flagged_ids).copy()

    author_counts = Counter(
        get_author(political[tweet_id])
        for tweet_id in flagged_ids
    )

    flagged_incident_edges = [
        (u, v, data)
        for u, v, data in graph.edges(data=True)
        if u in flagged_ids or v in flagged_ids
    ]

    flagged_internal_edges = [
        (u, v, data)
        for u, v, data in graph.edges(data=True)
        if u in flagged_ids and v in flagged_ids
    ]

    components = sorted(
        nx.weakly_connected_components(flagged_graph),
        key=len,
        reverse=True,
    )

    output.mkdir(parents=True, exist_ok=True)

    summary = {
        "political_posts": len(political),
        "annotated_posts_found": len(flagged_ids),
        "annotated_posts_missing": len(missing),
        "political_graph_nodes": graph.number_of_nodes(),
        "political_graph_edges": graph.number_of_edges(),
        "flagged_incident_edges": len(
            flagged_incident_edges
        ),
        "flagged_internal_edges": len(
            flagged_internal_edges
        ),
        "flagged_graph_components": len(components),
        "largest_flagged_component": (
            len(components[0]) if components else 0
        ),
        "top_flagged_authors": author_counts.most_common(10),
    }

    summary_path = (
        output / "political_graph_analysis_week3.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    csv_path = (
        output / "political_graph_authors_week3.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "username",
            "flagged_post_count",
        ])

        for username, count in author_counts.most_common():
            writer.writerow([username, count])

    edges_path = (
        output / "political_graph_flagged_edges_week3.csv"
    )

    with edges_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "source_tweet_id",
            "target_tweet_id",
            "relation",
            "source_flagged",
            "target_flagged",
        ])

        for u, v, data in flagged_incident_edges:
            writer.writerow([
                u,
                v,
                data["relation"],
                u in flagged_ids,
                v in flagged_ids,
            ])

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\nZapisano raporty w:", output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--annotations",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=Path("reports"),
    )

    args = parser.parse_args()

    analyze(
        args.source,
        args.annotations,
        args.out,
    )
