"""Analyze the combined REPLY, QUOTE and SHARED_HASHTAG post graph."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from experiments.compare_graph_variants import (
    load_posts,
    collection_for,
)
from x_graph_analysis.domain.models import RelationshipType
from x_graph_analysis.graph.builder import (
    RelationshipBuilder,
    NetworkXGraphBuilder,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "scweet_4weeks_merged.json"
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

PREFIX = "combined_post_graph_4weeks"

INTERACTION_TYPES = {
    RelationshipType.REPLY,
    RelationshipType.QUOTE,
}


def analyze(graph):
    """Compute structural statistics for a directed multigraph."""
    weak_components = list(nx.weakly_connected_components(graph))
    strong_components = list(nx.strongly_connected_components(graph))
    degrees = dict(graph.degree())

    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "isolated_nodes": nx.number_of_isolates(graph),
        "weak_components": len(weak_components),
        "largest_weak_component": max(
            (len(c) for c in weak_components),
            default=0,
        ),
        "strong_components": len(strong_components),
        "largest_strong_component": max(
            (len(c) for c in strong_components),
            default=0,
        ),
        "max_in_degree": max(
            (d for _, d in graph.in_degree()),
            default=0,
        ),
        "max_out_degree": max(
            (d for _, d in graph.out_degree()),
            default=0,
        ),
        "degree_distribution": dict(
            sorted(Counter(degrees.values()).items())
        ),
    }


def plot_comparison(results):
    labels = list(results)
    values = [
        results[name]["largest_weak_component"]
        for name in labels
    ]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(labels, values)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(value),
            ha="center",
            va="bottom",
        )

    ax.set_ylabel("Number of posts")
    ax.set_title("Largest weakly connected component")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    fig.savefig(
        REPORTS / f"{PREFIX}_component_comparison.png",
        dpi=180,
    )
    plt.close(fig)


def plot_degree_distribution(graph):
    degrees = [degree for _, degree in graph.degree()]
    counts = Counter(degrees)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.scatter(
        list(counts),
        list(counts.values()),
        s=18,
        alpha=0.7,
    )
    ax.set_xscale("symlog")
    ax.set_yscale("log")
    ax.set_xlabel("Total degree")
    ax.set_ylabel("Number of posts")
    ax.set_title("Combined post graph - degree distribution")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(
        REPORTS / f"{PREFIX}_degree_distribution.png",
        dpi=180,
    )
    plt.close(fig)



def plot_largest_component(component, communities):
    """Visualize the complete largest component with Louvain colors."""
    from matplotlib.lines import Line2D

    # Assign a community to each post.
    community_by_node = {
        node: index
        for index, members in enumerate(communities)
        for node in members
    }

    # Build an undirected, weighted layout graph.
    layout_graph = nx.Graph()
    layout_graph.add_nodes_from(sorted(component.nodes(), key=str))

    hashtag_edges = []
    reply_edges = []
    quote_edges = []

    for u, v, data in component.edges(data=True):
        relation = data["relationship_type"]

        if relation is RelationshipType.SHARED_HASHTAG:
            if str(u) > str(v):
                continue
            hashtag_edges.append((u, v))
            weight = data["weight"]
        elif relation is RelationshipType.REPLY:
            reply_edges.append((u, v))
            weight = 1
        elif relation is RelationshipType.QUOTE:
            quote_edges.append((u, v))
            weight = 1
        else:
            continue

        if layout_graph.has_edge(u, v):
            layout_graph[u][v]["weight"] += weight
        else:
            layout_graph.add_edge(u, v, weight=weight)

    positions = nx.spring_layout(
        layout_graph,
        weight="weight",
        seed=42,
        iterations=300,
        k=0.25,
    )

    fig, ax = plt.subplots(figsize=(16, 12))
    palette = plt.get_cmap("tab20")

    nx.draw_networkx_edges(
        layout_graph,
        positions,
        edgelist=hashtag_edges,
        ax=ax,
        edge_color="#9CA3AF",
        width=0.55,
        alpha=0.23,
    )

    for index, members in enumerate(communities):
        nx.draw_networkx_nodes(
            layout_graph,
            positions,
            nodelist=sorted(members, key=str),
            node_color=[palette(index)],
            node_size=48,
            edgecolors="white",
            linewidths=0.35,
            ax=ax,
            label=f"Community {index + 1} ({len(members)} posts)",
        )

    for edges, color in [
        (reply_edges, "#E67E22"),
        (quote_edges, "#D62728"),
    ]:
        nx.draw_networkx_edges(
            component,
            positions,
            edgelist=edges,
            edge_color=color,
            width=2.4,
            alpha=1,
            arrows=True,
            arrowsize=16,
            node_size=48,
            ax=ax,
        )

    ax.set_title(
        "Combined post graph - largest weak component\n"
        "298 posts | SHARED_HASHTAG weight >= 2",
        fontsize=15,
    )

    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1),
        fontsize=9,
        frameon=False,
    )
    ax.axis("off")

    output = REPORTS / f"{PREFIX}_largest_component_final.png"
    fig.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(fig)

    print("Final visualization saved:", output)



def main():
    posts, _ = load_posts(SOURCE)
    collection = collection_for(
        posts,
        set(posts),
        "four-weeks-combined-post-graph",
    )

    relationships = RelationshipBuilder().build(collection)

    counts = Counter(
        relationship.relationship_type.value
        for relationship in relationships
    )

    print("Posts:", len(posts))
    print("Logical relationships:", dict(counts))

    variants = {
        "Interactions": [
            r for r in relationships
            if r.relationship_type in INTERACTION_TYPES
        ],
        "Hashtags": [
            r for r in relationships
            if r.relationship_type is RelationshipType.SHARED_HASHTAG
        ],
        "Combined": [
            r for r in relationships
            if r.relationship_type in INTERACTION_TYPES
            or r.relationship_type is RelationshipType.SHARED_HASHTAG
        ],
        "Combined weight >= 2": [
            r for r in relationships
            if r.relationship_type in INTERACTION_TYPES
            or (
                r.relationship_type is RelationshipType.SHARED_HASHTAG
                and r.weight >= 2
            )
        ],
    }

    builder = NetworkXGraphBuilder()
    graphs = {
        name: builder.build(collection, selected)
        for name, selected in variants.items()
    }

    results = {
        name: analyze(graph)
        for name, graph in graphs.items()
    }

    for name, stats in results.items():
        print(
            f"{name}: "
            f"nodes={stats['nodes']}, "
            f"edges={stats['edges']}, "
            f"isolates={stats['isolated_nodes']}, "
            f"largest_weak_component="
            f"{stats['largest_weak_component']}"
        )

    report = {
        "source": str(SOURCE.relative_to(ROOT)),
        "post_count": len(posts),
        "logical_relationship_counts": dict(counts),
        "variants": results,
        "note": (
            "SHARED_HASHTAG is logically undirected, "
            "but represented by two directed arcs. "
            "REPOST relationships are excluded."
        ),
    }

    # Inspect the largest component of the filtered combined graph.
    filtered_graph = graphs["Combined weight >= 2"]
    largest_nodes = max(
        nx.weakly_connected_components(filtered_graph),
        key=len,
    )
    component = filtered_graph.subgraph(largest_nodes).copy()
    hashtag_counts = Counter(
        hashtag
        for node in component.nodes()
        for hashtag in component.nodes[node]["hashtags"]
    )

    print("Top hashtags in largest component:")
    for hashtag, count in hashtag_counts.most_common(15):
        print(f"  #{hashtag}: {count} posts")
    component_types = Counter(
        data["relationship_type"].value
        for _, _, data in component.edges(data=True)
    )

    print()
    print("LARGEST COMPONENT - COMBINED WEIGHT >= 2")
    print("Nodes:", component.number_of_nodes())
    print("Directed arcs:", component.number_of_edges())
    print("Relationship types:", dict(component_types))

    # Build an undirected projection for community detection.
    # Count each logical hashtag relationship only once.
    community_graph = nx.Graph()
    community_graph.add_nodes_from(component.nodes())

    for u, v, data in component.edges(data=True):
        relation = data["relationship_type"]

        if relation is RelationshipType.SHARED_HASHTAG:
            # Each hashtag relationship is stored in both directions.
            # Keep only one copy of each logical relationship.
            if str(u) > str(v):
                continue

        weight = (
            data["weight"]
            if relation is RelationshipType.SHARED_HASHTAG
            else 1
        )

        if community_graph.has_edge(u, v):
            community_graph[u][v]["weight"] += weight
        else:
            community_graph.add_edge(u, v, weight=weight)


    # Canonical node and edge order for reproducible Louvain results.
    stable_graph = nx.Graph()
    stable_graph.add_nodes_from(
        sorted(community_graph.nodes(), key=str)
    )

    stable_edges = sorted(
        community_graph.edges(data=True),
        key=lambda edge: (
            min(str(edge[0]), str(edge[1])),
            max(str(edge[0]), str(edge[1])),
        ),
    )

    for u, v, data in stable_edges:
        stable_graph.add_edge(
            u,
            v,
            weight=data["weight"],
        )

    communities = nx.community.louvain_communities(
        stable_graph,
        weight="weight",
        seed=42,
    )

    
    communities = sorted(
        communities,
        key=len,
        reverse=True,
    )
    modularity = nx.community.modularity(
        community_graph,
        communities,
        weight="weight",
    )

    print(f"Louvain modularity: {modularity:.4f}")
    print()
    print("LOUVAIN COMMUNITIES")
    print("Number of communities:", len(communities))

    for index, members in enumerate(communities, start=1):
        hashtags = Counter(
            hashtag
            for node in members
            for hashtag in component.nodes[node]["hashtags"]
        )

        print(
            f"Community {index}: "
            f"{len(members)} posts | "
            f"Top hashtags: {hashtags.most_common(5)}"
        )

    report["largest_filtered_component"] = {
        "nodes": component.number_of_nodes(),
        "directed_arcs": component.number_of_edges(),
        "relationship_types": dict(component_types),
    }

    output = REPORTS / f"{PREFIX}.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    plot_comparison(results)
    plot_degree_distribution(graphs["Combined"])
    plot_largest_component(component, communities)
    print(f"Report saved: {output}")
    print("Charts saved in reports/")


if __name__ == "__main__":
    main()

