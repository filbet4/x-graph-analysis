"""Inspect the multidomain Scweet experiment offline."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_PATH = PROJECT_ROOT / "data" / "scweet_multidomain_sample.json"


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


def main() -> None:
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    items = data["records"]

    by_id = {
        str(item["tweet_id"]): item
        for item in items
    }
    ids = set(by_id)

    domain_counts: Counter[str] = Counter()
    query_counts: Counter[str] = Counter()

    multi_query_posts = 0
    multi_domain_sampling_posts = 0

    reply_count = 0
    quote_count = 0
    repost_count = 0

    internal_reply_edges: list[tuple[str, str]] = []
    internal_quote_edges: list[tuple[str, str]] = []
    internal_repost_edges: list[tuple[str, str]] = []

    missing_reply_targets: set[str] = set()
    missing_quote_targets: set[str] = set()
    missing_repost_targets: set[str] = set()

    hashtags: Counter[str] = Counter()
    mentions: Counter[str] = Counter()

    cross_sampling_edges: list[
        tuple[str, str, str, set[str], set[str]]
    ] = []

    for tweet_id, item in by_id.items():
        sources = item.get("sampling_sources", [])

        source_domains = {
            source["domain"]
            for source in sources
        }

        source_queries = {
            source["query"]
            for source in sources
        }

        for domain in source_domains:
            domain_counts[domain] += 1

        for query in source_queries:
            query_counts[query] += 1

        if len(source_queries) > 1:
            multi_query_posts += 1

        if len(source_domains) > 1:
            multi_domain_sampling_posts += 1

        record = get_record(item)

        for hashtag in record.get("hashtags") or []:
            if isinstance(hashtag, str):
                hashtags[hashtag.lower()] += 1
            elif isinstance(hashtag, dict):
                value = hashtag.get("text") or hashtag.get("tag")
                if value:
                    hashtags[str(value).lower()] += 1

        for mention in record.get("mentions") or []:
            if isinstance(mention, str):
                mentions[mention.lower()] += 1
            elif isinstance(mention, dict):
                value = (
                    mention.get("username")
                    or mention.get("screen_name")
                )
                if value:
                    mentions[str(value).lower()] += 1

        reply_target = record.get("in_reply_to_tweet_id")

        if reply_target:
            reply_count += 1
            reply_target = str(reply_target)

            if reply_target in ids:
                internal_reply_edges.append(
                    (tweet_id, reply_target)
                )
            else:
                missing_reply_targets.add(reply_target)

        quote_target = get_quote_target(record)

        if quote_target:
            quote_count += 1

            if quote_target in ids:
                internal_quote_edges.append(
                    (tweet_id, quote_target)
                )
            else:
                missing_quote_targets.add(quote_target)

        repost_target = get_repost_target(record)

        if repost_target:
            repost_count += 1

            if repost_target in ids:
                internal_repost_edges.append(
                    (tweet_id, repost_target)
                )
            else:
                missing_repost_targets.add(repost_target)

    all_internal_edges = (
        [("reply", *edge) for edge in internal_reply_edges]
        + [("quote", *edge) for edge in internal_quote_edges]
        + [("repost", *edge) for edge in internal_repost_edges]
    )

    for relation, source_id, target_id in all_internal_edges:
        source_domains = {
            source["domain"]
            for source in by_id[source_id]["sampling_sources"]
        }
        target_domains = {
            source["domain"]
            for source in by_id[target_id]["sampling_sources"]
        }

        if source_domains != target_domains:
            cross_sampling_edges.append(
                (
                    relation,
                    source_id,
                    target_id,
                    source_domains,
                    target_domains,
                )
            )

    print("=== DATASET ===")
    print(f"Unique posts: {len(ids)}")

    print()
    print("Posts by sampling domain:")
    for domain, count in sorted(domain_counts.items()):
        print(f"  {domain}: {count}")

    print()
    print("Posts by query:")
    for query, count in sorted(query_counts.items()):
        print(f"  {query}: {count}")

    print()
    print(f"Posts found by multiple queries: {multi_query_posts}")
    print(
        "Posts found through multiple sampling domains: "
        f"{multi_domain_sampling_posts}"
    )

    print()
    print("=== RELATIONSHIPS ===")
    print(f"Posts that are replies: {reply_count}")
    print(f"Posts that are quotes: {quote_count}")
    print(f"Posts that are reposts: {repost_count}")

    print()
    print(f"Internal REPLY edges: {len(internal_reply_edges)}")
    print(f"Internal QUOTE edges: {len(internal_quote_edges)}")
    print(f"Internal REPOST edges: {len(internal_repost_edges)}")
    print(f"Total internal edges: {len(all_internal_edges)}")

    print()
    print(f"Missing reply targets: {len(missing_reply_targets)}")
    print(f"Missing quote targets: {len(missing_quote_targets)}")
    print(f"Missing repost targets: {len(missing_repost_targets)}")

    print()
    print(
        "Internal edges crossing sampling domains: "
        f"{len(cross_sampling_edges)}"
    )

    for (
        relation,
        source_id,
        target_id,
        source_domains,
        target_domains,
    ) in cross_sampling_edges[:10]:
        print(
            f"  {relation}: {source_id} {source_domains} "
            f"-> {target_id} {target_domains}"
        )

    print()
    print("=== CONTENT SIGNALS ===")

    print("Most common hashtags:")
    for hashtag, count in hashtags.most_common(15):
        print(f"  #{hashtag}: {count}")

    print()
    print("Most common mentions:")
    for mention, count in mentions.most_common(15):
        print(f"  @{mention}: {count}")


if __name__ == "__main__":
    main()