"""Inspect the conversation-centric Scweet sample."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "scweet_conversation_sample.json"


def get_quote_target(record: dict[str, Any]) -> str | None:
    quoted = record.get("quoted_tweet")
    if isinstance(quoted, dict) and quoted.get("tweet_id"):
        return str(quoted["tweet_id"])

    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    value = legacy.get("quoted_status_id_str")
    return str(value) if value else None


def get_repost_target(record: dict[str, Any]) -> str | None:
    retweeted = record.get("retweeted_tweet")
    if isinstance(retweeted, dict) and retweeted.get("tweet_id"):
        return str(retweeted["tweet_id"])

    return None


def main() -> None:
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

    records = data["records"]
    root_ids = {str(value) for value in data["root_ids"]}

    by_id = {
        str(record["tweet_id"]): record
        for record in records
        if record.get("tweet_id")
    }

    ids = set(by_id)

    reply_edges: list[tuple[str, str]] = []
    quote_edges: list[tuple[str, str]] = []
    repost_edges: list[tuple[str, str]] = []

    missing_reply_targets: set[str] = set()
    missing_quote_targets: set[str] = set()
    missing_repost_targets: set[str] = set()

    replies = 0
    quotes = 0
    reposts = 0

    for tweet_id, record in by_id.items():
        reply_target = record.get("in_reply_to_tweet_id")

        if reply_target:
            replies += 1
            reply_target = str(reply_target)

            if reply_target in ids:
                reply_edges.append((tweet_id, reply_target))
            else:
                missing_reply_targets.add(reply_target)

        quote_target = get_quote_target(record)

        if quote_target:
            quotes += 1

            if quote_target in ids:
                quote_edges.append((tweet_id, quote_target))
            else:
                missing_quote_targets.add(quote_target)

        repost_target = get_repost_target(record)

        if repost_target:
            reposts += 1

            if repost_target in ids:
                repost_edges.append((tweet_id, repost_target))
            else:
                missing_repost_targets.add(repost_target)

    all_edges = reply_edges + quote_edges + repost_edges

    participating_nodes: set[str] = set()

    for source, target in all_edges:
        participating_nodes.add(source)
        participating_nodes.add(target)

    participation_percentage = (
        100 * len(participating_nodes) / len(ids)
        if ids
        else 0.0
    )

    # Temporary undirected graph for connected components.
    adjacency: dict[str, set[str]] = defaultdict(set)

    for tweet_id in ids:
        adjacency[tweet_id]

    for source, target in all_edges:
        adjacency[source].add(target)
        adjacency[target].add(source)

    visited: set[str] = set()
    component_sizes: list[int] = []

    for node in ids:
        if node in visited:
            continue

        queue = deque([node])
        visited.add(node)
        size = 0

        while queue:
            current = queue.popleft()
            size += 1

            for neighbour in adjacency[current]:
                if neighbour not in visited:
                    visited.add(neighbour)
                    queue.append(neighbour)

        component_sizes.append(size)

    component_sizes.sort(reverse=True)

    print("=== GLOBAL RESULTS ===")
    print(f"Total unique posts: {len(ids)}")
    print(f"Root posts: {len(root_ids)}")
    print()
    print(f"Posts that are replies: {replies}")
    print(f"Posts that are quotes: {quotes}")
    print(f"Posts that are reposts: {reposts}")
    print()
    print(f"Internal REPLY edges: {len(reply_edges)}")
    print(f"Internal QUOTE edges: {len(quote_edges)}")
    print(f"Internal REPOST edges: {len(repost_edges)}")
    print(f"Total internal edges: {len(all_edges)}")
    print()
    print(f"Missing reply targets: {len(missing_reply_targets)}")
    print(f"Missing quote targets: {len(missing_quote_targets)}")
    print(f"Missing repost targets: {len(missing_repost_targets)}")
    print(
        "Total unique missing targets: "
        f"{len(missing_reply_targets | missing_quote_targets | missing_repost_targets)}"
    )
    print()
    print(f"Nodes participating in internal edges: {len(participating_nodes)}")
    print(f"Participation: {participation_percentage:.1f}%")
    print()
    print(f"Connected components: {len(component_sizes)}")
    print(
        "Largest component sizes: "
        f"{component_sizes[:10]}"
    )

    print()
    print("=== PER ROOT ===")

    conversations = data.get("conversations", {})

    for root_id in data["root_ids"]:
        root_id = str(root_id)

        conversation_ids = {
            str(tweet_id)
            for tweet_id in conversations.get(root_id, [])
        }
        conversation_ids.add(root_id)

        conversation_ids &= ids

        internal_replies = [
            (source, target)
            for source, target in reply_edges
            if source in conversation_ids and target in conversation_ids
        ]

        parent_of = {
            source: target
            for source, target in internal_replies
        }

        def depth(node: str) -> int | None:
            seen: set[str] = set()
            current = node
            result = 0

            while current != root_id:
                if current in seen:
                    return None

                seen.add(current)

                parent = parent_of.get(current)
                if parent is None:
                    return None

                current = parent
                result += 1

            return result

        depths = [
            value
            for node in conversation_ids
            if (value := depth(node)) is not None
        ]

        missing_parents = {
            str(by_id[node]["in_reply_to_tweet_id"])
            for node in conversation_ids
            if by_id[node].get("in_reply_to_tweet_id")
            and str(by_id[node]["in_reply_to_tweet_id"]) not in conversation_ids
        }

        print()
        print(f"Root: {root_id}")
        print(f"  Collected posts: {len(conversation_ids)}")
        print(f"  Internal reply edges: {len(internal_replies)}")
        print(f"  Maximum reconstructable reply depth: {max(depths, default=0)}")
        print(f"  Missing parent posts: {len(missing_parents)}")


if __name__ == "__main__":
    main()