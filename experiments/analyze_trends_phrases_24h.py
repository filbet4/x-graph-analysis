
"""Analyze frequently occurring phrases in 24-hour publication windows."""

import csv
import re
from collections import Counter, defaultdict
from datetime import UTC, timedelta
from pathlib import Path

from sklearn.feature_extraction.text import CountVectorizer

from compare_graph_variants import DOMAINS, load_posts

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "common_time_window"
OUT = ROOT / "reports" / "trends_24h"
OUT.mkdir(parents=True, exist_ok=True)

STOPWORDS = {
    "jest", "tego", "przez", "który", "która", "które",
    "oraz", "jako", "tylko", "bardzo", "może", "będzie",
    "było", "byli", "mamy", "tutaj", "takie", "też",
    "nie", "się", "ale", "dla", "jak", "czy", "już",
    "ten", "tym", "tak", "nad", "pod", "bez", "ich",
    "jego", "jej", "oni", "one", "nas", "was", "to",
    "na", "do", "od", "po", "za", "ze", "we", "że",
    "the", "and", "https", "http",
}


def clean(text):
    text = re.sub(r"https?://\S+", " ", text.lower())
    text = re.sub(r"@\w+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def main():
    rows = []

    for week in ("week1", "week2", "week3"):
        posts, domains = load_posts(DATA / f"{week}.json")
        t0 = min(p.published_at.astimezone(UTC) for p in posts.values())

        windows = defaultdict(list)
        for post in posts.values():
            index = int(
                (post.published_at.astimezone(UTC) - t0)
                // timedelta(hours=24)
            )
            windows[index].append(post)

        for domain in DOMAINS:
            previous = Counter()

            for index in sorted(windows):
                selected = [
                    p for p in windows[index]
                    if domain in domains.get(p.post_id, set())
                ]

                if not selected:
                    previous = Counter()
                    continue

                texts = [clean(p.text) for p in selected]

                vectorizer = CountVectorizer(
                    ngram_range=(2, 3),
                    min_df=1,
                    binary=True,
                    stop_words=list(STOPWORDS),
                    token_pattern=r"(?u)\b\w\w+\b",
                )

                try:
                    matrix = vectorizer.fit_transform(texts)
                except ValueError:
                    previous = Counter()
                    continue

                counts = Counter({
                    phrase: int(count)
                    for phrase, count in zip(
                        vectorizer.get_feature_names_out(),
                        matrix.sum(axis=0).A1,
                    )
                })

                for phrase, count in counts.most_common(30):
                    rows.append({
                        "week": week,
                        "window": index + 1,
                        "domain": domain,
                        "phrase": phrase,
                        "post_count": count,
                        "previous_count": previous.get(phrase, 0),
                        "change": count - previous.get(phrase, 0),
                    })

                previous = counts

    path = OUT / "trends_24h_phrases.csv"

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "week", "window", "domain", "phrase",
                "post_count", "previous_count", "change",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {path}: {len(rows)} rows")


if __name__ == "__main__":
    main()
