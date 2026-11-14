
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import networkx as nx


def tweet_id(item: dict) -> str:
    record = item.get("record") or {}
    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    return str(
        item.get("tweet_id")
        or record.get("tweet_id")
        or record.get("id")
        or legacy.get("id_str")
        or raw.get("rest_id")
        or ""
    ).strip()


def author_info(item: dict) -> tuple[str, str]:
    record = item.get("record") or {}
    raw = record.get("raw") or {}

    result = (
        ((raw.get("core") or {}).get("user_results") or {})
        .get("result") or {}
    )

    core = result.get("core") or {}
    legacy = result.get("legacy") or {}

    user_id = str(
        result.get("rest_id")
        or legacy.get("id_str")
        or ""
    )

    username = str(
        core.get("screen_name")
        or legacy.get("screen_name")
        or "unknown"
    )

    return user_id, username


def relations(item: dict) -> list[tuple[str, str]]:
    record = item.get("record") or {}
    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    result = []

    reply = legacy.get("in_reply_to_status_id_str")
    quote = legacy.get("quoted_status_id_str")

    if reply:
        result.append(("REPLY", str(reply)))

    if quote:
        result.append(("QUOTE", str(quote)))

    return result


def load_flagged(path: Path) -> dict[str, dict]:
    result = {}

    with path.open(
        encoding="utf-8-sig",
        newline="",
    ) as file:
        for row in csv.DictReader(file):
            post_id = str(row.get("tweet_id") or "").strip()

            if post_id:
                result[post_id] = row

    return result


def analyze(
    source: Path,
    annotations_path: Path,
    output: Path,
) -> None:
    payload = json.loads(
        source.read_text(encoding="utf-8")
    )

    records = payload["records"]

    flagged = load_flagged(annotations_path)
    flagged_ids = set(flagged)

    posts = {}

    for item in records:
        post_id = tweet_id(item)

        if post_id:
            posts[post_id] = item

    graph = nx.MultiDiGraph()

    for post_id, item in posts.items():
        user_id, username = author_info(item)

        graph.add_node(
            post_id,
            user_id=user_id,
            username=username,
            flagged=post_id in flagged_ids,
        )

    for post_id, item in posts.items():
        for relation, target in relations(item):
            if target in posts:
                graph.add_edge(
                    post_id,
                    target,
                    relation=relation,
                )

    found_flagged = flagged_ids & set(posts)
    missing_flagged = flagged_ids - set(posts)

    incident_edges = [
        (source_id, target_id, data)
        for source_id, target_id, data
        in graph.edges(data=True)
        if (
            source_id in found_flagged
            or target_id in found_flagged
        )
    ]

    internal_edges = [
        (source_id, target_id, data)
        for source_id, target_id, data
        in incident_edges
        if (
            source_id in found_flagged
            and target_id in found_flagged
        )
    ]

    neighbors = set()

    for source_id, target_id, _ in incident_edges:
        if source_id not in found_flagged:
            neighbors.add(source_id)

        if target_id not in found_flagged:
            neighbors.add(target_id)

    flagged_authors = {
        graph.nodes[post_id]["user_id"]
        for post_id in found_flagged
        if graph.nodes[post_id]["user_id"]
    }

    author_post_counts = Counter(
        graph.nodes[post_id]["user_id"]
        for post_id in graph.nodes
        if graph.nodes[post_id]["user_id"]
    )

    flagged_author_activity = {
        author_id: author_post_counts[author_id]
        for author_id in flagged_authors
    }

    connected_flagged = {
        post_id
        for source_id, target_id, _ in incident_edges
        for post_id in (source_id, target_id)
        if post_id in found_flagged
    }

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary = {
        "total_posts": len(posts),
        "total_edges": graph.number_of_edges(),
        "flagged_found": len(found_flagged),
        "flagged_missing": len(missing_flagged),
        "incident_edges": len(incident_edges),
        "internal_flagged_edges": len(internal_edges),
        "flagged_posts_with_connections": len(
            connected_flagged
        ),
        "distinct_neighbor_posts": len(neighbors),
        "flagged_authors_with_id": len(flagged_authors),
        "flagged_author_total_posts": sum(
            flagged_author_activity.values()
        ),
        "top_flagged_author_activity": sorted(
            flagged_author_activity.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )[:10],
    }

    summary_path = (
        output / "flagged_neighborhood_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    edges_path = (
        output / "flagged_neighborhood_edges.csv"
    )

    with edges_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.writer(file)

        writer.writerow([
            "source_id",
            "target_id",
            "relation",
            "source_flagged",
            "target_flagged",
            "source_author",
            "target_author",
        ])

        for source_id, target_id, data in incident_edges:
            writer.writerow([
                source_id,
                target_id,
                data["relation"],
                source_id in found_flagged,
                target_id in found_flagged,
                graph.nodes[source_id]["username"],
                graph.nodes[target_id]["username"],
            ])

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    print("\nZapisano:", summary_path)
    print("Zapisano:", edges_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--annotations",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--out",
        default=Path("reports"),
        type=Path,
    )

    args = parser.parse_args()

    analyze(
        args.source,
        args.annotations,
        args.out,
    )
