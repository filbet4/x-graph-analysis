"""Inspect the large raw Scweet dataset.

This script performs exploratory analysis of the collected raw dataset.
It intentionally does not use the production graph/domain model.

The goal is to inspect the real data first and use the results to decide:
- how REPLY, QUOTE and REPOST should be represented,
- how incomplete interaction targets are,
- whether one-hop target retrieval is necessary,
- whether SHARED_HASHTAG should be treated as a graph relationship
  or analysed separately.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Callable

import networkx as nx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "data" / "scweet_large_sample.json"


def load_dataset() -> dict[str, Any]:
    """Load the large Scweet dataset."""

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def get_record(item: dict[str, Any]) -> dict[str, Any]:
    """Return the raw Scweet record."""

    record = item.get("record", {})

    if isinstance(record, dict):
        return record

    return {}


def get_tweet_id(item: dict[str, Any]) -> str | None:
    """Return normalized tweet ID."""

    tweet_id = item.get("tweet_id")

    if tweet_id is None:
        tweet_id = get_record(item).get("tweet_id")

    if tweet_id is None:
        return None

    return str(tweet_id)


def get_author_id(record: dict[str, Any]) -> str | None:
    """Extract author ID from a Scweet record."""

    user = record.get("user")

    candidates = [
        record.get("user_id"),
        record.get("author_id"),
        user.get("user_id") if isinstance(user, dict) else None,
        user.get("id") if isinstance(user, dict) else None,
    ]

    for candidate in candidates:
        if candidate is not None:
            return str(candidate)

    raw = record.get("raw")

    if isinstance(raw, dict):
        core = raw.get("core")

        if isinstance(core, dict):
            user_results = core.get("user_results")

            if isinstance(user_results, dict):
                result = user_results.get("result")

                if isinstance(result, dict):
                    rest_id = result.get("rest_id")

                    if rest_id:
                        return str(rest_id)

    return None


def get_created_at(record: dict[str, Any]) -> datetime | None:
    """Extract and parse tweet creation timestamp."""

    value = None

    for key in ("created_at", "date", "timestamp"):
        if record.get(key):
            value = record[key]
            break

    if value is None:
        raw = record.get("raw")

        if isinstance(raw, dict):
            legacy = raw.get("legacy")

            if isinstance(legacy, dict):
                value = legacy.get("created_at")

    if not value:
        return None

    value = str(value)

    formats = (
        "%a %b %d %H:%M:%S %z %Y",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
    )

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return None


def get_language(record: dict[str, Any]) -> str | None:
    """Extract language reported in the raw record."""

    for key in ("lang", "language"):
        value = record.get(key)

        if value:
            return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get("lang")

            if value:
                return str(value)

    return None


def get_reply_target(record: dict[str, Any]) -> str | None:
    """Extract the tweet ID this post replies to."""

    value = record.get("in_reply_to_tweet_id")

    if value:
        return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get("in_reply_to_status_id_str")

            if value:
                return str(value)

    return None


def get_quote_target(record: dict[str, Any]) -> str | None:
    """Extract the quoted tweet ID."""

    quoted_tweet = record.get("quoted_tweet")

    if isinstance(quoted_tweet, dict):
        value = quoted_tweet.get("tweet_id")

        if value:
            return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            value = legacy.get("quoted_status_id_str")

            if value:
                return str(value)

    return None


def get_repost_target(record: dict[str, Any]) -> str | None:
    """Extract the reposted tweet ID."""

    for key in (
        "retweeted_tweet_id",
        "repost_tweet_id",
    ):
        value = record.get(key)

        if value:
            return str(value)

    retweeted_tweet = record.get("retweeted_tweet")

    if isinstance(retweeted_tweet, dict):
        value = retweeted_tweet.get("tweet_id")

        if value:
            return str(value)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            retweeted_status = legacy.get("retweeted_status_result")

            if isinstance(retweeted_status, dict):
                result = retweeted_status.get("result")

                if isinstance(result, dict):
                    value = (
                        result.get("rest_id")
                        or result.get("id_str")
                    )

                    if value:
                        return str(value)

    return None


def normalize_hashtag(value: Any) -> str | None:
    """Normalize a hashtag representation."""

    if isinstance(value, str):
        text = value.strip().lstrip("#")

        if text:
            return text.lower()

    if isinstance(value, dict):
        text = (
            value.get("text")
            or value.get("tag")
            or value.get("name")
        )

        if text:
            return str(text).strip().lstrip("#").lower()

    return None


def get_hashtags(record: dict[str, Any]) -> set[str]:
    """Extract normalized hashtags."""

    hashtags: set[str] = set()

    direct = record.get("hashtags")

    if isinstance(direct, list):
        for value in direct:
            hashtag = normalize_hashtag(value)

            if hashtag:
                hashtags.add(hashtag)

    raw = record.get("raw")

    if isinstance(raw, dict):
        legacy = raw.get("legacy")

        if isinstance(legacy, dict):
            entities = legacy.get("entities")

            if isinstance(entities, dict):
                raw_hashtags = entities.get("hashtags")

                if isinstance(raw_hashtags, list):
                    for value in raw_hashtags:
                        hashtag = normalize_hashtag(value)

                        if hashtag:
                            hashtags.add(hashtag)

    return hashtags


def analyse_sampling(
    records: list[dict[str, Any]],
) -> None:
    """Analyse sampling domains and queries."""

    domain_counts: Counter[str] = Counter()
    query_counts: Counter[str] = Counter()
    multi_source_posts = 0

    for item in records:
        sources = item.get("sampling_sources", [])

        if not isinstance(sources, list):
            continue

        if len(sources) > 1:
            multi_source_posts += 1

        domains = {
            source.get("domain")
            for source in sources
            if isinstance(source, dict) and source.get("domain")
        }

        queries = {
            source.get("query")
            for source in sources
            if isinstance(source, dict) and source.get("query")
        }

        domain_counts.update(domains)
        query_counts.update(queries)

    print()
    print("=" * 70)
    print("SAMPLING")
    print("=" * 70)

    print("Posts by sampling domain:")

    for domain, count in domain_counts.most_common():
        print(f"  {domain:<20} {count}")

    print()
    print("Posts by query:")

    for query, count in query_counts.most_common():
        print(f"  {query:<40} {count}")

    print()
    print(
        "Posts found through multiple sampling sources: "
        f"{multi_source_posts}"
    )


def analyse_basic_metadata(
    records: list[dict[str, Any]],
) -> None:
    """Analyse authors, languages and timestamps."""

    authors: set[str] = set()
    missing_author = 0

    languages: Counter[str] = Counter()
    timestamps: list[datetime] = []

    for item in records:
        record = get_record(item)

        author_id = get_author_id(record)

        if author_id:
            authors.add(author_id)
        else:
            missing_author += 1

        language = get_language(record)

        if language:
            languages[language] += 1
        else:
            languages["UNKNOWN"] += 1

        created_at = get_created_at(record)

        if created_at:
            timestamps.append(created_at)

    print()
    print("=" * 70)
    print("BASIC METADATA")
    print("=" * 70)

    print(f"Unique authors: {len(authors)}")
    print(f"Posts without detected author: {missing_author}")

    print()
    print("Languages:")

    for language, count in languages.most_common():
        percentage = (
            count / len(records) * 100
            if records
            else 0
        )

        print(
            f"  {language:<15} "
            f"{count:>6} "
            f"({percentage:6.2f}%)"
        )

    print()

    if timestamps:
        print(
            "Earliest timestamp: "
            f"{min(timestamps).isoformat()}"
        )
        print(
            "Latest timestamp:   "
            f"{max(timestamps).isoformat()}"
        )
        print(
            "Successfully parsed timestamps: "
            f"{len(timestamps)}/{len(records)}"
        )
    else:
        print("No timestamps could be parsed.")


def inspect_repost_structure(
    records: list[dict[str, Any]],
) -> None:
    """Inspect actual values of repost-related Scweet fields."""

    is_retweet_true = 0
    is_retweet_false = 0
    is_retweet_other = 0

    retweeted_tweet_dict = 0
    retweeted_tweet_nonempty = 0
    retweeted_tweet_empty = 0
    retweeted_tweet_none = 0
    retweeted_tweet_other = 0

    actual_repost_examples: list[
        tuple[str, Any, Any]
    ] = []

    for item in records:
        record = get_record(item)
        tweet_id = get_tweet_id(item) or "UNKNOWN"

        # ----------------------------------------------------------
        # is_retweet
        # ----------------------------------------------------------

        is_retweet = record.get("is_retweet")

        if is_retweet is True:
            is_retweet_true += 1

        elif is_retweet is False:
            is_retweet_false += 1

        else:
            is_retweet_other += 1

        # ----------------------------------------------------------
        # retweeted_tweet
        # ----------------------------------------------------------

        retweeted_tweet = record.get("retweeted_tweet")

        if retweeted_tweet is None:
            retweeted_tweet_none += 1

        elif isinstance(retweeted_tweet, dict):
            retweeted_tweet_dict += 1

            if retweeted_tweet:
                retweeted_tweet_nonempty += 1
            else:
                retweeted_tweet_empty += 1

        else:
            retweeted_tweet_other += 1

        # ----------------------------------------------------------
        # Examples of records that may actually be reposts
        # ----------------------------------------------------------

        looks_like_repost = (
            is_retweet is True
            or (
                isinstance(retweeted_tweet, dict)
                and bool(retweeted_tweet)
            )
        )

        if (
            looks_like_repost
            and len(actual_repost_examples) < 10
        ):
            target_id = None

            if isinstance(retweeted_tweet, dict):
                target_id = (
                    retweeted_tweet.get("tweet_id")
                    or retweeted_tweet.get("id")
                    or retweeted_tweet.get("id_str")
                )

            actual_repost_examples.append(
                (
                    tweet_id,
                    is_retweet,
                    target_id,
                )
            )

    print()
    print("=" * 70)
    print("REPOST VALUE INSPECTION")
    print("=" * 70)

    print("is_retweet:")
    print(
        f"  True:                  "
        f"{is_retweet_true}"
    )
    print(
        f"  False:                 "
        f"{is_retweet_false}"
    )
    print(
        f"  Missing/other:         "
        f"{is_retweet_other}"
    )

    print()
    print("retweeted_tweet:")

    print(
        f"  Dict total:            "
        f"{retweeted_tweet_dict}"
    )
    print(
        f"  Non-empty dict:        "
        f"{retweeted_tweet_nonempty}"
    )
    print(
        f"  Empty dict:            "
        f"{retweeted_tweet_empty}"
    )
    print(
        f"  None:                  "
        f"{retweeted_tweet_none}"
    )
    print(
        f"  Other value:           "
        f"{retweeted_tweet_other}"
    )

    print()
    print("Potential actual repost records:")
    print(
        f"  By is_retweet=True:    "
        f"{is_retweet_true}"
    )
    print(
        f"  By non-empty target:   "
        f"{retweeted_tweet_nonempty}"
    )

    print()
    print("Examples:")

    if not actual_repost_examples:
        print(
            "  No records look like actual reposts."
        )

    else:
        for (
            tweet_id,
            is_retweet,
            target_id,
        ) in actual_repost_examples:
            print()
            print(f"  Tweet ID:        {tweet_id}")
            print(f"  is_retweet:      {is_retweet}")
            print(f"  target tweet ID: {target_id}")


def analyse_relationship(
    name: str,
    records: list[dict[str, Any]],
    corpus_ids: set[str],
    target_getter: Callable[[dict[str, Any]], str | None],
) -> tuple[list[tuple[str, str]], set[str]]:
    """Analyse one relationship type."""

    edges: list[tuple[str, str]] = []
    missing_targets: set[str] = set()

    total = 0
    internal = 0
    external = 0
    self_relations = 0

    for item in records:
        source_id = get_tweet_id(item)

        if source_id is None:
            continue

        record = get_record(item)
        target_id = target_getter(record)

        if target_id is None:
            continue

        total += 1
        edges.append((source_id, target_id))

        if source_id == target_id:
            self_relations += 1

        if target_id in corpus_ids:
            internal += 1
        else:
            external += 1
            missing_targets.add(target_id)

    completeness = (
        internal / total * 100
        if total
        else 0
    )

    print()
    print(name)
    print("-" * 70)
    print(f"Total relationships:        {total}")
    print(f"Internal targets:           {internal}")
    print(f"External targets:           {external}")
    print(
        "Unique missing targets:     "
        f"{len(missing_targets)}"
    )
    print(
        f"Internal completeness:      "
        f"{completeness:.2f}%"
    )
    print(f"Self-relations:             {self_relations}")

    return edges, missing_targets


def print_graph_stats(
    name: str,
    edges: list[tuple[str, str]],
    corpus_ids: set[str],
) -> None:
    """Print basic statistics for a directed internal graph."""

    graph = nx.DiGraph()

    for source, target in edges:
        if source in corpus_ids and target in corpus_ids:
            graph.add_edge(source, target)

    print()
    print(name)
    print("-" * 70)
    print(
        "Nodes participating in graph: "
        f"{graph.number_of_nodes()}"
    )
    print(
        f"Edges:                        "
        f"{graph.number_of_edges()}"
    )

    if graph.number_of_nodes() == 0:
        print("Density:                      0")
        print("Weak components:              0")
        print("Strong components:            0")
        print("Largest weak component:       0")
        return

    weak_components = list(
        nx.weakly_connected_components(graph)
    )

    strong_components = list(
        nx.strongly_connected_components(graph)
    )

    largest_weak = max(
        (
            len(component)
            for component in weak_components
        ),
        default=0,
    )

    print(
        "Density:                      "
        f"{nx.density(graph):.8f}"
    )
    print(
        "Weak components:              "
        f"{len(weak_components)}"
    )
    print(
        "Strong components:            "
        f"{len(strong_components)}"
    )
    print(
        "Largest weak component:       "
        f"{largest_weak}"
    )

    in_degrees = dict(graph.in_degree())
    out_degrees = dict(graph.out_degree())

    if in_degrees:
        print(
            "Maximum in-degree:             "
            f"{max(in_degrees.values())}"
        )

    if out_degrees:
        print(
            "Maximum out-degree:            "
            f"{max(out_degrees.values())}"
        )


def analyse_hashtags(
    records: list[dict[str, Any]],
) -> None:
    """Analyse hashtag usage and potential hashtag graph size."""

    hashtag_counts: Counter[str] = Counter()

    hashtag_posts: defaultdict[
        str,
        set[str],
    ] = defaultdict(set)

    posts_with_hashtags = 0

    for item in records:
        tweet_id = get_tweet_id(item)

        if tweet_id is None:
            continue

        hashtags = get_hashtags(
            get_record(item)
        )

        if hashtags:
            posts_with_hashtags += 1

        for hashtag in hashtags:
            hashtag_counts[hashtag] += 1
            hashtag_posts[hashtag].add(tweet_id)

    potential_pairs: set[tuple[str, str]] = set()

    for post_ids in hashtag_posts.values():
        if len(post_ids) < 2:
            continue

        for first, second in combinations(
            sorted(post_ids),
            2,
        ):
            potential_pairs.add(
                (first, second)
            )

    print()
    print("=" * 70)
    print("HASHTAGS")
    print("=" * 70)

    percentage = (
        posts_with_hashtags / len(records) * 100
        if records
        else 0
    )

    print(
        "Posts with hashtags:       "
        f"{posts_with_hashtags} "
        f"({percentage:.2f}%)"
    )

    print(
        "Unique hashtags:           "
        f"{len(hashtag_counts)}"
    )

    print(
        "Potential unique post pairs connected "
        "by SHARED_HASHTAG: "
        f"{len(potential_pairs)}"
    )

    print()
    print("Top 20 hashtags:")

    for hashtag, count in hashtag_counts.most_common(20):
        print(f"  #{hashtag:<30} {count}")


def main() -> None:
    """Run exploratory analysis."""

    data = load_dataset()

    records = data.get("records", [])

    if not isinstance(records, list):
        raise ValueError(
            "Dataset field 'records' must be a list."
        )

    corpus_ids = {
        tweet_id
        for item in records
        if isinstance(item, dict)
        if (tweet_id := get_tweet_id(item))
        is not None
    }

    print("=" * 70)
    print("LARGE SCWEET DATASET ANALYSIS")
    print("=" * 70)

    print(f"Dataset: {DATA_PATH}")
    print(f"Records: {len(records)}")
    print(f"Unique tweet IDs: {len(corpus_ids)}")

    metadata = data.get("metadata", {})

    if not isinstance(metadata, dict):
        metadata = {}

    print(
        "Collection status: "
        f"{metadata.get('collection_status')}"
    )

    print(
        "Requested window: "
        f"{metadata.get('since')} -> "
        f"{metadata.get('until')}"
    )

    analyse_sampling(records)

    analyse_basic_metadata(records)

    inspect_repost_structure(records)

    print()
    print("=" * 70)
    print("RELATIONSHIPS")
    print("=" * 70)

    reply_edges, reply_missing = analyse_relationship(
        "REPLY",
        records,
        corpus_ids,
        get_reply_target,
    )

    quote_edges, quote_missing = analyse_relationship(
        "QUOTE",
        records,
        corpus_ids,
        get_quote_target,
    )

    repost_edges, repost_missing = analyse_relationship(
        "REPOST",
        records,
        corpus_ids,
        get_repost_target,
    )

    analyse_hashtags(records)

    print()
    print("=" * 70)
    print("DIRECTED INTERNAL GRAPHS")
    print("=" * 70)

    print_graph_stats(
        "G_reply",
        reply_edges,
        corpus_ids,
    )

    print_graph_stats(
        "G_quote",
        quote_edges,
        corpus_ids,
    )

    print_graph_stats(
        "G_repost",
        repost_edges,
        corpus_ids,
    )

    all_missing = (
        reply_missing
        | quote_missing
        | repost_missing
    )

    overlap_reply_quote = (
        reply_missing
        & quote_missing
    )

    print()
    print("=" * 70)
    print("ONE-HOP TARGET RETRIEVAL CANDIDATES")
    print("=" * 70)

    print(
        "Missing REPLY targets:  "
        f"{len(reply_missing)}"
    )

    print(
        "Missing QUOTE targets:  "
        f"{len(quote_missing)}"
    )

    print(
        "Missing REPOST targets: "
        f"{len(repost_missing)}"
    )

    print(
        "REPLY/QUOTE target overlap: "
        f"{len(overlap_reply_quote)}"
    )

    print(
        "Unique missing targets across all types: "
        f"{len(all_missing)}"
    )

    print()
    print("=" * 70)
    print("ANALYSIS FINISHED")
    print("=" * 70)


if __name__ == "__main__":
    main()