"""Analyze the REPLY/QUOTE post interaction graph for week 3."""

import json
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx

from experiments.compare_graph_variants import load_posts, collection_for
from x_graph_analysis.domain.models import RelationshipType
from x_graph_analysis.graph.builder import RelationshipBuilder, NetworkXGraphBuilder


SOURCE = Path("data/scweet_4weeks_merged.json")
OUTPUT = Path("reports")
OUTPUT.mkdir(exist_ok=True)

posts, domains = load_posts(SOURCE)
collection = collection_for(posts, set(posts), "week3-interactions")

all_relationships = RelationshipBuilder().build(collection)
relationships = tuple(
    r for r in all_relationships
    if r.relationship_type in (RelationshipType.REPLY, RelationshipType.QUOTE)
)

graph = NetworkXGraphBuilder().build(collection, relationships)

weak_components = sorted(
    nx.weakly_connected_components(graph),
    key=len,
    reverse=True,
)
strong_components = list(nx.strongly_connected_components(graph))

in_degrees = [degree for _, degree in graph.in_degree()]
out_degrees = [degree for _, degree in graph.out_degree()]

metrics = {
    "source": str(SOURCE),
    "graph_type": "directed_post_interactions",
    "included_relationships": ["REPLY", "QUOTE"],
    "nodes": graph.number_of_nodes(),
    "edges": graph.number_of_edges(),
    "edges_by_type": dict(
        Counter(data["relationship_type"].value for _, _, data in graph.edges(data=True))
    ),
    "isolated_nodes": nx.number_of_isolates(graph),
    "weak_components": len(weak_components),
    "largest_weak_component": len(weak_components[0]) if weak_components else 0,
    "strong_components": len(strong_components),
    "largest_strong_component": max(map(len, strong_components), default=0),
    "density": nx.density(graph),
    "max_in_degree": max(in_degrees, default=0),
    "max_out_degree": max(out_degrees, default=0),
}

(OUTPUT / "post_interactions_4weeks.json").write_text(
    json.dumps(metrics, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

# Degree distribution
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

for ax, degrees, title in (
    (axes[0], in_degrees, "In-degree distribution"),
    (axes[1], out_degrees, "Out-degree distribution"),
):
    counts = Counter(degrees)
    ax.bar(sorted(counts), [counts[k] for k in sorted(counts)])
    ax.set_title(title)
    ax.set_xlabel("Degree")
    ax.set_ylabel("Number of posts")
    ax.set_yscale("log")

fig.tight_layout()
fig.savefig(OUTPUT / "post_interactions_4weeks_degree_distribution.png", dpi=200)
plt.close(fig)

# Largest weakly connected component
if weak_components:
    largest = graph.subgraph(weak_components[0]).copy()
    fig, ax = plt.subplots(figsize=(10, 8))
    pos = nx.spring_layout(largest, seed=42)
    nx.draw_networkx(
        largest,
        pos=pos,
        ax=ax,
        with_labels=False,
        node_size=45,
        width=0.8,
        arrows=True,
        arrowsize=8,
    )
    ax.set_title("Largest weakly connected component - REPLY/QUOTE")
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(OUTPUT / "post_interactions_4weeks_largest_component.png", dpi=200)
    plt.close(fig)


# Degree distribution excluding zero-degree vertices
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

for ax, degrees, title in (
    (axes[0], in_degrees, "In-degree distribution (degree > 0)"),
    (axes[1], out_degrees, "Out-degree distribution (degree > 0)"),
):
    counts = Counter(degree for degree in degrees if degree > 0)
    values = sorted(counts)
    ax.bar(values, [counts[k] for k in values])
    ax.set_title(title)
    ax.set_xlabel("Degree")
    ax.set_ylabel("Number of posts")
    ax.set_yscale("log")

fig.tight_layout()
fig.savefig(
    OUTPUT / "post_interactions_4weeks_active_degree_distribution.png",
    dpi=200,
)
plt.close(fig)

print(json.dumps(metrics, indent=2, ensure_ascii=False))
print("Saved results in reports/")
