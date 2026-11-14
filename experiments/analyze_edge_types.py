
import csv
from collections import Counter
from pathlib import Path

from compare_graph_variants import DOMAINS, load_posts, post_graph


SOURCES = {
    "week1": Path("data/common_time_window/week1.json"),
    "week2": Path("data/common_time_window/week2.json"),
    "week3": Path("data/common_time_window/week3.json"),
}

OUTPUT = Path("reports/edge_types_common_window.csv")

EDGE_TYPES = (
    "reply",
    "quote",
    "repost",
    "shared_hashtag",
    "mention",
)


def analyze(week, scope, posts, post_ids):
    graph, relationships = post_graph(posts, post_ids)

    # Logical relationships before graph conversion.
    relation_counts = Counter(
        relationship.relationship_type.value
        for relationship in relationships
    )

    # Actual directed edges stored in MultiDiGraph.
    edge_counts = Counter(
        data["relationship_type"].value
        for _, _, data in graph.edges(data=True)
    )

    row = {
        "week": week,
        "scope": scope,
        "post_count": len(post_ids),
        "node_count": graph.number_of_nodes(),
        "relationship_count": len(relationships),
        "edge_count": graph.number_of_edges(),
    }

    for edge_type in EDGE_TYPES:
        row[f"{edge_type}_relationships"] = (
            relation_counts[edge_type]
        )
        row[f"{edge_type}_edges"] = (
            edge_counts[edge_type]
        )

    row["direct_interaction_edges"] = sum(
        edge_counts[t]
        for t in ("reply", "quote", "repost")
    )

    row["shared_hashtag_share_pct"] = round(
        100 * edge_counts["shared_hashtag"]
        / graph.number_of_edges(),
        2,
    ) if graph.number_of_edges() else 0.0

    # One shared hashtag relationship creates two edges.
    assert (
        edge_counts["shared_hashtag"]
        == 2 * relation_counts["shared_hashtag"]
    )

    assert sum(edge_counts.values()) == graph.number_of_edges()

    return row


def main():
    rows = []

    for week, source in SOURCES.items():
        posts, domains = load_posts(source)

        all_ids = set(posts)

        scopes = {"all": all_ids}

        for domain in DOMAINS:
            scopes[domain] = {
                post_id
                for post_id in all_ids
                if domain in domains.get(post_id, set())
            }

        for scope, post_ids in scopes.items():
            row = analyze(week, scope, posts, post_ids)
            rows.append(row)

            print(
                week,
                scope,
                "posts:", row["post_count"],
                "edges:", row["edge_count"],
                "shared hashtag:",
                f'{row["shared_hashtag_share_pct"]}%',
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)

    print()
    print("Saved:", OUTPUT)


if __name__ == "__main__":
    main()
