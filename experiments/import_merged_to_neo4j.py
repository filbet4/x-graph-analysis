"""Import all merged Scweet batches into the existing Neo4j graph."""

import json
from collections import Counter
from pathlib import Path

from x_graph_analysis.adapters.persistence.neo4j import Neo4jGraphRepository
from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper
from x_graph_analysis.config import Settings

PATH = Path("data/scweet_merged_all_batches.json")


def main():
    settings = Settings.from_environment()

    if settings.neo4j_database != "xgraph-expanded":
        raise RuntimeError(
            f"Wrong database: {settings.neo4j_database}. "
            "Expected xgraph-expanded."
        )

    if not settings.neo4j_password:
        raise RuntimeError("Neo4j password is not configured.")

    items = json.loads(PATH.read_text(encoding="utf-8"))["records"]
    mapper = ScweetPostMapper()

    posts = []
    relationships = set()
    available_ids = {str(item["tweet_id"]) for item in items}

    for item in items:
        pid = str(item["tweet_id"])
        record = item["record"]

        if isinstance(record.get("raw"), dict):
            post = mapper.map_seed({
                "tweet_id": pid,
                "record": record,
            })
        else:
            post = mapper.map_target(record)

        posts.append(post)

        raw = record.get("raw", record)

        if raw.get("__typename") == "TweetWithVisibilityResults":
            raw = raw.get("tweet", raw)

        legacy = raw.get("legacy", {})

        reply = (
            record.get("in_reply_to_tweet_id")
            or legacy.get("in_reply_to_status_id_str")
        )

        quoted = record.get("quoted_tweet")
        quote = (
            (quoted.get("tweet_id") if isinstance(quoted, dict) else None)
            or legacy.get("quoted_status_id_str")
        )

        for kind, target in (("REPLY", reply), ("QUOTE", quote)):
            if target and str(target) in available_ids:
                relationships.add((pid, str(target), kind))

    counts = Counter(kind for _, _, kind in relationships)

    print("Posts:", len(posts))
    print("REPLY:", counts["REPLY"])
    print("QUOTE:", counts["QUOTE"])

    if (
        len(posts) != 13885
        or counts["REPLY"] != 5185
        or counts["QUOTE"] != 937
    ):
        raise RuntimeError("Validation failed. Import cancelled.")

    repository = Neo4jGraphRepository(
        uri=settings.neo4j_uri,
        user=settings.neo4j_user,
        password=settings.neo4j_password,
        database=settings.neo4j_database,
    )

    try:
        repository.verify_connectivity()
        repository.create_constraints()

        print("Importing posts...")
        repository.save_posts(posts)

        print("Importing relationships...")
        repository.save_post_relationships([
            {
                "source_post_id": source,
                "target_post_id": target,
                "type": kind,
            }
            for source, target, kind in sorted(relationships)
        ])

        print("Import finished successfully.")

    finally:
        repository.close()


if __name__ == "__main__":
    main()
