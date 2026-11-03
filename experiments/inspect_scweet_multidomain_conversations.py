"""Inspect the multidomain conversation sample offline."""

from __future__ import annotations

import json
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "scweet_multidomain_conversations.json"
)


def get_record(item: dict[str, Any]) -> dict[str, Any]:
    return item["record"]


def get_quote_target(record: dict[str, Any]) -> str | None:
    quoted = record.get("quoted_tweet")

    if isinstance(quoted, dict) and quoted.get("tweet_id"):
        return str(quoted["tweet_id"])

    raw = record.get("raw") or {}
    legacy = raw.get("legacy") or {}

    target = legacy.get("quoted_status_id_str")

    return str(target) if target else None


def get_repost_target(record: dict[str, Any]) -> str | None:
    retweeted = record.get("retweeted_tweet")

    if isinstance(retweeted, dict) and retweeted.get("tweet_id"):
        return str(retweeted["tweet_id"])

    return None


def get_domains(item: dict[str, Any]) -> set[str]:
    return {
        context["sampling_domain"]
        for context in item.get("collection_contexts", [])
    }


def get_root_ids(item: dict[str, Any]) -> set[str]:
    return {
        str(context["root_id"])
        for context in item.get("collection_contexts", [])
    }


def maximum_reply_depth(
    root_id: str,
    children: dict[str, list[str]],
) -> int:
    queue = deque([(root_id, 0)])
    visited = {root_id}
    maximum = 0

    while queue:
        current, depth = queue.popleft()
        maximum = max(maximum, depth)

        for child in children.get(current, []):
            if child not in visited:
                visited.add(child)
                queue.append((child, depth + 1))

    return maximum


def main() -> None:
    data = json.loads(
        INPUT_PATH.read_text(encoding="utf-8")
    )

    items = data["records"]

    by_id = {
        str(item["tweet_id"]): item
        for item in items
    }

    ids = set(by_id)

    selected_roots = {
        str(root["tweet_id"]): root
        for root in data["selected_roots"]
    }

    reply_edges: list[tuple[str, str]] = []
    quote_edges: list[tuple[str, str]] = []
    repost_edges: list[tuple[str, str]] = []

    missing_reply_targets: set[str] = set()
    missing_quote_targets: set[str] = set()
    missing_repost_targets: set[str] = set()

    replies_total = 0
    quotes_total = 0
    reposts_total = 0

    children: dict[str, list[str]] = defaultdict(list)

    domain_post_counts: Counter[str] = Counter()
    domain_edge_counts: Counter[str] = Counter()

    cross_domain_edges = []

    for tweet_id, item in by_id.items():
        record = get_record(item)

        for domain in get_domains(item):
            domain_post_counts[domain] += 1

        reply_target = record.get("in_reply_to_tweet_id")

        if reply_target:
            replies_total += 1
            reply_target = str(reply_target)

            if reply_target in ids:
                reply_edges.append(
                    (tweet_id, reply_target)
                )
                children[reply_target].append(tweet_id)
            else:
                missing_reply_targets.add(reply_target)

        quote_target = get_quote_target(record)

        if quote_target:
            quotes_total += 1

            if quote_target in ids:
                quote_edges.append(
                    (tweet_id, quote_target)
                )
            else:
                missing_quote_targets.add(quote_target)

        repost_target = get_repost_target(record)

        if repost_target:
            reposts_total += 1

            if repost_target in ids:
                repost_edges.append(
                    (tweet_id, repost_target)
                )
            else:
                missing_repost_targets.add(repost_target)

    all_edges = (
        [("reply", source, target) for source, target in reply_edges]
        + [("quote", source, target) for source, target in quote_edges]
        + [("repost", source, target) for source, target in repost_edges]
    )

    for relation, source, target in all_edges:
        source_domains = get_domains(by_id[source])
        target_domains = get_domains(by_id[target])

        for domain in source_domains & target_domains:
            domain_edge_counts[domain] += 1

        if source_domains != target_domains:
            cross_domain_edges.append(
                (
                    relation,
                    source,
                    target,
                    source_domains,
                    target_domains,
                )
            )

    multi_conversation_posts = sum(
        1
        for item in items
        if len(get_root_ids(item)) > 1
    )

    multi_sampling_domain_posts = sum(
        1
        for item in items
        if len(get_domains(item)) > 1
    )

    print("=== GLOBAL RESULTS ===")
    print(f"Unique posts: {len(ids)}")
    print(f"Selected roots: {len(selected_roots)}")

    print()
    print("Posts by collection domain:")
    for domain, count in sorted(domain_post_counts.items()):
        print(f"  {domain}: {count}")

    print()
    print(f"Posts that are replies: {replies_total}")
    print(f"Posts that are quotes: {quotes_total}")
    print(f"Posts that are reposts: {reposts_total}")

    print()
    print(f"Internal REPLY edges: {len(reply_edges)}")
    print(f"Internal QUOTE edges: {len(quote_edges)}")
    print(f"Internal REPOST edges: {len(repost_edges)}")
    print(f"Total internal edges: {len(all_edges)}")

    print()
    print(
        f"Missing reply targets: "
        f"{len(missing_reply_targets)}"
    )
    print(
        f"Missing quote targets: "
        f"{len(missing_quote_targets)}"
    )
    print(
        f"Missing repost targets: "
        f"{len(missing_repost_targets)}"
    )

    print()
    print(
        "Posts occurring in multiple conversations: "
        f"{multi_conversation_posts}"
    )
    print(
        "Posts occurring in multiple collection domains: "
        f"{multi_sampling_domain_posts}"
    )

    print()
    print(
        "Internal edges crossing collection domains: "
        f"{len(cross_domain_edges)}"
    )

    print()
    print("Internal edges by collection domain:")
    for domain, count in sorted(domain_edge_counts.items()):
        print(f"  {domain}: {count}")

    print()
    print("=== PER ROOT ===")

    for root_id, root_info in selected_roots.items():
        domain = root_info["sampling_domain"]

        conversation_ids = {
            tweet_id
            for tweet_id, item in by_id.items()
            if root_id in get_root_ids(item)
        }

        internal_replies = sum(
            1
            for source, target in reply_edges
            if source in conversation_ids
            and target in conversation_ids
        )

        depth = maximum_reply_depth(
            root_id,
            children,
        )

        print()
        print(f"Root: {root_id}")
        print(f"  Collection domain: {domain}")
        print(
            f"  Collected posts: "
            f"{len(conversation_ids)}"
        )
        print(
            f"  Internal reply edges: "
            f"{internal_replies}"
        )
        print(
            f"  Maximum reconstructable reply depth: "
            f"{depth}"
        )

    if cross_domain_edges:
        print()
        print("=== CROSS-DOMAIN COLLECTION EDGES ===")

        for (
            relation,
            source,
            target,
            source_domains,
            target_domains,
        ) in cross_domain_edges[:20]:
            print(
                f"{relation}: {source} {source_domains} "
                f"-> {target} {target_domains}"
            )


if __name__ == "__main__":
    main()