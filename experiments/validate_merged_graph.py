"""Validate all merged Scweet posts and relationships."""

import json
from collections import Counter
from pathlib import Path

from x_graph_analysis.adapters.sources.scweet import ScweetPostMapper

PATH = Path("data/scweet_merged_all_batches.json")


def main():
    data = json.loads(PATH.read_text(encoding="utf-8"))
    items = data["records"]
    mapper = ScweetPostMapper()

    posts = []
    errors = []
    relationships = set()
    available_ids = {str(item["tweet_id"]) for item in items}

    for item in items:
        pid = str(item["tweet_id"])
        record = item["record"]

        try:
            if isinstance(record.get("raw"), dict):
                post = mapper.map_seed({
                    "tweet_id": pid,
                    "record": record,
                })
            else:
                post = mapper.map_target(record)

            posts.append(post)

        except (ValueError, TypeError, KeyError) as exc:
            errors.append((pid, str(exc)))

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

    print("Records:", len(items))
    print("Mapped posts:", len(posts))
    print("Mapping errors:", len(errors))
    print("REPLY:", counts["REPLY"])
    print("QUOTE:", counts["QUOTE"])
    print("Total relationships:", len(relationships))

    if errors:
        print("\nFirst 5 mapping errors:")
        for error in errors[:5]:
            print(error)


if __name__ == "__main__":
    main()
