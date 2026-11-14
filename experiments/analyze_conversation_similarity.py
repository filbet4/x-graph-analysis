"""Analyze weighted hashtag similarity between X conversations."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "data" / "scweet_4weeks_merged.json"
REPORTS = ROOT / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

PREFIX = "conversation_similarity_4weeks"


def get_conversation_id(item):
    record = item["record"]
    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    cid = (
        legacy.get("conversation_id_str")
        or raw.get("conversation_id")
        or record.get("conversation_id")
    )

    if cid:
        return str(cid)

    if record.get("in_reply_to_tweet_id"):
        return None

    return str(item["tweet_id"])


def normalize_hashtags(record):
    result = set()

    for tag in record.get("hashtags") or []:
        if isinstance(tag, str):
            name = tag
        elif isinstance(tag, dict):
            name = str(tag.get("text") or "")
        else:
            continue

        name = name.lstrip("#").strip().casefold()

        if name:
            result.add(name)

    return result


def load_conversations():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    conversations = defaultdict(set)
    excluded = 0
    included = 0

    for item in data["records"]:
        cid = get_conversation_id(item)

        if cid is None:
            excluded += 1
            continue

        included += 1
        conversations[cid].update(
            normalize_hashtags(item["record"])
        )

    return conversations, included, excluded


def build_weighted_graph(conversations):
    graph = nx.Graph()
    graph.add_nodes_from(conversations)

    inverted_index = defaultdict(set)

    for cid, tags in conversations.items():
        for tag in tags:
            inverted_index[tag].add(cid)

    weights = Counter()

    for ids in inverted_index.values():
        for pair in combinations(sorted(ids), 2):
            weights[pair] += 1

    for (source, target), weight in weights.items():
        graph.add_edge(source, target, weight=weight)

    return graph, inverted_index


def analyze_graph(graph):
    components = list(nx.connected_components(graph))
    degrees = dict(graph.degree())
    active = [node for node, degree in degrees.items() if degree > 0]

    largest = max(components, key=len) if components else set()

    return {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "isolated_nodes": nx.number_of_isolates(graph),
        "active_nodes": len(active),
        "components": len(components),
        "largest_component": len(largest),
        "density": nx.density(graph),
        "average_degree": (
            sum(degrees.values()) / len(degrees)
            if degrees else 0
        ),
        "max_degree": max(degrees.values(), default=0),
        "degree_distribution": dict(
            sorted(Counter(degrees.values()).items())
        ),
    }


def plot_degree_distribution(graph):
    degrees = [degree for _, degree in graph.degree()]
    active_degrees = [degree for degree in degrees if degree > 0]

    for name, values, title in [
        ("degree_distribution", degrees, "All conversations"),
        ("active_degree_distribution", active_degrees, "Active conversations"),
    ]:
        counts = Counter(values)

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(
            list(counts.keys()),
            list(counts.values()),
            s=18,
            alpha=0.7,
        )
        ax.set_xscale("symlog" if 0 in counts else "log")
        ax.set_yscale("log")
        ax.set_xlabel("Degree")
        ax.set_ylabel("Number of conversations")
        ax.set_title(f"Degree distribution - {title}")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(REPORTS / f"{PREFIX}_{name}.png", dpi=180)
        plt.close(fig)


def plot_weight_distribution(graph):
    counts = Counter(
        data["weight"]
        for _, _, data in graph.edges(data=True)
    )

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(
        list(sorted(counts)),
        [counts[weight] for weight in sorted(counts)],
    )
    ax.set_yscale("log")
    ax.set_xlabel("Number of shared hashtags (edge weight)")
    ax.set_ylabel("Number of edges (log scale)")
    ax.set_title("Conversation similarity - edge weights")
    fig.tight_layout()
    fig.savefig(
        REPORTS / f"{PREFIX}_weight_distribution.png",
        dpi=180,
    )
    plt.close(fig)

    return dict(sorted(counts.items()))


def plot_largest_component(graph):
    components = nx.connected_components(graph)
    largest = max(components, key=len, default=set())

    if not largest:
        return

    subgraph = graph.subgraph(largest).copy()

    # A reduced visualization avoids drawing thousands of labels.
    if subgraph.number_of_nodes() > 250:
        selected = sorted(
            subgraph.degree(),
            key=lambda item: item[1],
            reverse=True,
        )[:250]
        subgraph = subgraph.subgraph(
            [node for node, _ in selected]
        ).copy()

    positions = nx.spring_layout(
        subgraph,
        seed=42,
        iterations=50,
    )

    fig, ax = plt.subplots(figsize=(12, 10))

    nx.draw_networkx(
        subgraph,
        pos=positions,
        ax=ax,
        node_size=18,
        width=0.25,
        alpha=0.65,
        with_labels=False,
    )

    ax.set_title(
        "Largest connected component "
        "(up to 250 highest-degree nodes)"
    )
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(
        REPORTS / f"{PREFIX}_largest_component.png",
        dpi=180,
    )
    plt.close(fig)


def main():
    conversations, included, excluded = load_conversations()
    graph, inverted_index = build_weighted_graph(conversations)

    results = {
        "source": str(INPUT.relative_to(ROOT)),
        "included_posts": included,
        "excluded_posts": excluded,
        "conversations": len(conversations),
        "unique_hashtags": len(inverted_index),
        "thresholds": {},
    }

    for threshold in (1, 2, 3):
        filtered = nx.Graph()
        filtered.add_nodes_from(graph.nodes())

        filtered.add_edges_from(
            (u, v, data)
            for u, v, data in graph.edges(data=True)
            if data["weight"] >= threshold
        )

        results["thresholds"][str(threshold)] = (
            analyze_graph(filtered)
        )

        stats = results["thresholds"][str(threshold)]

        print(
            f"Threshold >= {threshold}: "
            f"nodes={stats['nodes']}, "
            f"edges={stats['edges']}, "
            f"isolates={stats['isolated_nodes']}, "
            f"largest_component={stats['largest_component']}"
        )

    results["weight_distribution"] = (
        plot_weight_distribution(graph)
    )

    results["top_hashtags"] = Counter({
        tag: len(ids)
        for tag, ids in inverted_index.items()
    }).most_common(20)

    plot_degree_distribution(graph)
    plot_largest_component(graph)

    output = REPORTS / f"{PREFIX}.json"
    output.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nReport saved: {output}")
    print("Charts saved in reports/")


if __name__ == "__main__":
    main()
