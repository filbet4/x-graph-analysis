"""Compare heterogeneous, user, and post graph variants locally."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import networkx as nx

from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper
from x_graph_analysis.analysis.analyzer import NetworkAnalyzer
from x_graph_analysis.domain.models import (
    Post,
    PostCollection,
    RelationshipType,
)
from x_graph_analysis.graph.builder import NetworkXGraphBuilder, RelationshipBuilder

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = (
    PROJECT_ROOT / "data" / "scweet_large_sample_2026-10-21_2026-10-27.json"
)
DEFAULT_JSON = PROJECT_ROOT / "reports" / "graph_variant_comparison_week3.json"
DEFAULT_CSV = PROJECT_ROOT / "reports" / "graph_variant_comparison_week3.csv"
DOMAINS = ("politics", "sport", "pop_culture")
INTERACTION_TYPES = (
    RelationshipType.REPLY,
    RelationshipType.QUOTE,
    RelationshipType.REPOST,
)


def load_posts(path: Path) -> tuple[dict[str, Post], dict[str, set[str]]]:
    """Map Search records and retain sampling-domain membership separately."""
    data = json.loads(path.read_text(encoding="utf-8"))
    mapper = ScweetPostMapper()
    posts: dict[str, Post] = {}
    domains: dict[str, set[str]] = {}
    for item in data["records"]:
        post = mapper.map_seed(item)
        posts[post.post_id] = post
        sources = item.get("sampling_sources", [])
        domains[post.post_id] = {
            str(source["domain"])
            for source in sources
            if isinstance(source, dict) and source.get("domain") in DOMAINS
        }
    return posts, domains


def collection_for(
    posts: dict[str, Post],
    post_ids: set[str],
    source_name: str,
) -> PostCollection:
    """Build a deterministic collection without modifying source data."""
    selected = tuple(posts[post_id] for post_id in sorted(post_ids))
    collected_at = max(
        (post.published_at for post in selected),
        default=datetime.now(UTC),
    )
    return PostCollection(
        posts=selected,
        source_name=source_name,
        collected_at=collected_at,
    )


def post_graph(
    posts: dict[str, Post],
    post_ids: set[str],
) -> tuple[nx.MultiDiGraph[Any, Any], tuple[Any, ...]]:
    """Build the existing post graph and its detected relationships."""
    collection = collection_for(posts, post_ids, "week3-post-graph")
    relationships = RelationshipBuilder().build(collection)
    graph = NetworkXGraphBuilder().build(collection, relationships)
    return graph, relationships


def heterogeneous_graph(
    posts: dict[str, Post],
    post_ids: set[str],
    relationships: tuple[Any, ...],
) -> nx.MultiDiGraph[Any, Any]:
    """Build User-Post-Hashtag graph using only existing domain facts."""
    graph: nx.MultiDiGraph[Any, Any] = nx.MultiDiGraph()
    for post_id in sorted(post_ids):
        post = posts[post_id]
        post_node = f"post:{post.post_id}"
        user_node = f"user:{post.author.user_id}"
        graph.add_node(post_node, node_type="Post", created_at=post.published_at)
        graph.add_node(user_node, node_type="User")
        graph.add_edge(user_node, post_node, relationship_type="AUTHORED", weight=1)
        for hashtag in post.hashtags:
            hashtag_node = f"hashtag:{hashtag.normalized_text}"
            graph.add_node(hashtag_node, node_type="Hashtag")
            graph.add_edge(
                post_node,
                hashtag_node,
                relationship_type="HAS_HASHTAG",
                weight=1,
            )
    for relationship in relationships:
        if relationship.relationship_type not in INTERACTION_TYPES:
            continue
        graph.add_edge(
            f"post:{relationship.source_post_id}",
            f"post:{relationship.target_post_id}",
            relationship_type=relationship.relationship_type.value,
            weight=1,
        )
    return graph


def user_graph(
    posts: dict[str, Post],
    relationships: tuple[Any, ...],
) -> nx.MultiDiGraph[Any, Any]:
    """Project only real post interactions onto distinct authors."""
    graph: nx.MultiDiGraph[Any, Any] = nx.MultiDiGraph()
    for post in posts.values():
        graph.add_node(post.author.user_id, node_type="User")
    weights: Counter[tuple[str, str, str]] = Counter()
    for relationship in relationships:
        if relationship.relationship_type not in INTERACTION_TYPES:
            continue
        source_author = posts[relationship.source_post_id].author.user_id
        target_author = posts[relationship.target_post_id].author.user_id
        if source_author == target_author:
            continue
        weights[
            (source_author, target_author, relationship.relationship_type.value)
        ] += 1
    for (source, target, relationship_type), weight in sorted(weights.items()):
        graph.add_edge(
            source,
            target,
            relationship_type=relationship_type,
            weight=weight,
        )
    return graph


def graph_metrics(graph: nx.MultiDiGraph[Any, Any]) -> dict[str, Any]:
    """Serialize existing NetworkAnalyzer metrics plus weighted edge totals."""
    analyzer = NetworkAnalyzer()
    result = analyzer.analyze(graph)
    node_metrics = result.node_metrics
    weak_sizes = sorted(
        (len(component) for component in result.weakly_connected_components),
        reverse=True,
    )
    strong_sizes = sorted(
        (len(component) for component in result.strongly_connected_components),
        reverse=True,
    )
    degrees = [metric.degree for metric in node_metrics]
    pagerank = sorted(
        ((score.node_id, score.score) for score in result.pagerank),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "node_count": result.statistics.node_count,
        "edge_count": result.statistics.edge_count,
        "weighted_interaction_count": sum(
            int(data.get("weight", 1)) for _, _, data in graph.edges(data=True)
        ),
        "density": result.statistics.density,
        "isolated_node_count": result.statistics.isolated_node_count,
        "weak_component_count": len(weak_sizes),
        "largest_weak_component": weak_sizes[0] if weak_sizes else 0,
        "strong_component_count": len(strong_sizes),
        "largest_strong_component": strong_sizes[0] if strong_sizes else 0,
        "degree_mean": sum(degrees) / len(degrees) if degrees else 0.0,
        "degree_median": median(degrees) if degrees else 0.0,
        "degree_max": max(degrees, default=0),
        "top_pagerank": [
            {"node_id": node_id, "score": score} for node_id, score in pagerank[:10]
        ],
    }


def interaction_coverage(
    posts: dict[str, Post],
    post_ids: set[str],
) -> dict[str, int]:
    """Count references and missing targets without inventing relationships."""
    references = Counter()
    missing = Counter()
    for post_id in post_ids:
        post = posts[post_id]
        for name, target in (
            ("REPLY", post.reply_to_post_id),
            ("QUOTE", post.quoted_post_id),
            ("REPOST", post.reposted_post_id),
        ):
            if target:
                references[name] += 1
                if target not in post_ids:
                    missing[name] += 1
    return {
        "reply_references": references["REPLY"],
        "quote_references": references["QUOTE"],
        "repost_references": references["REPOST"],
        "missing_reply_targets": missing["REPLY"],
        "missing_quote_targets": missing["QUOTE"],
        "missing_repost_targets": missing["REPOST"],
    }


def analyze_scope(
    posts: dict[str, Post],
    scope: str,
    post_ids: set[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Analyze all three variants for one global or domain scope."""
    graph, relationships = post_graph(posts, post_ids)
    hetero = heterogeneous_graph(posts, post_ids, relationships)
    projected_users = user_graph(
        {post_id: posts[post_id] for post_id in post_ids},
        relationships,
    )
    rows: list[dict[str, Any]] = []
    variant_graphs = {
        "heterogeneous": hetero,
        "users": projected_users,
        "posts": graph,
    }
    metrics = {
        variant: graph_metrics(value) for variant, value in variant_graphs.items()
    }
    for variant, values in metrics.items():
        rows.append(
            {
                "scope": scope,
                "variant": variant,
                **{
                    key: value for key, value in values.items() if key != "top_pagerank"
                },
                "top_pagerank": json.dumps(values["top_pagerank"], ensure_ascii=False),
            }
        )
    return {
        "post_count": len(post_ids),
        "author_count": len({posts[post_id].author.user_id for post_id in post_ids}),
        "hashtag_count": len(
            {
                tag.normalized_text
                for post_id in post_ids
                for tag in posts[post_id].hashtags
            }
        ),
        "interaction_coverage": interaction_coverage(posts, post_ids),
        "variants": metrics,
    }, rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    """Write flattened metric rows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "scope",
        "variant",
        "node_count",
        "edge_count",
        "weighted_interaction_count",
        "density",
        "isolated_node_count",
        "weak_component_count",
        "largest_weak_component",
        "strong_component_count",
        "largest_strong_component",
        "degree_mean",
        "degree_median",
        "degree_max",
        "top_pagerank",
    ]
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def run(source: Path, json_path: Path, csv_path: Path) -> dict[str, Any]:
    """Run the local comparison for the full cohort and each domain."""
    posts, domains = load_posts(source)
    all_ids = set(posts)
    scopes = {"all": all_ids}
    for domain in DOMAINS:
        scopes[domain] = {
            post_id
            for post_id, post_domains in domains.items()
            if domain in post_domains
        }
    scope_results: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    for scope, post_ids in scopes.items():
        result, scope_rows = analyze_scope(posts, scope, post_ids)
        scope_results[scope] = result
        rows.extend(scope_rows)
    timestamps = [post.published_at for post in posts.values()]
    report = {
        "metadata": {
            "source": str(source),
            "post_count": len(posts),
            "published_at_min": min(timestamps).isoformat(),
            "published_at_max": max(timestamps).isoformat(),
            "tn_minus_t0_hours": 24,
            "reaction_24h_observations_available": False,
            "reaction_24h_note": (
                "No per-post observed_at snapshot at published_at + 24h was found; "
                "historical counters are not used as 24h reactions."
            ),
            "domain_overlap_post_count": sum(
                len(post_domains) > 1 for post_domains in domains.values()
            ),
            "relationship_semantics": {
                "REPLY": "direct post reference",
                "QUOTE": "direct post reference",
                "REPOST": "direct post reference",
                "SHARED_HASHTAG": "thematic similarity only",
            },
        },
        "scopes": scope_results,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(rows, csv_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    args = parser.parse_args()
    report = run(args.source, args.json, args.csv)
    print(
        json.dumps(
            {
                "source": report["metadata"]["source"],
                "post_count": report["metadata"]["post_count"],
                "json": str(args.json),
                "csv": str(args.csv),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
