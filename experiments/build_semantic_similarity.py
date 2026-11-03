
"""Build semantic similarity relationships between conversations."""

import re

import numpy as np
from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

from x_graph_analysis.config import Settings


DATABASE = "xgraph-expanded"
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
THRESHOLD = 0.80
TOP_K = 5
BATCH_SIZE = 32


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"@\w+", " ", text)
    return " ".join(text.split())


def main() -> None:
    settings = Settings.from_environment()

    if not settings.neo4j_password:
        raise RuntimeError("Brak hasla Neo4j w konfiguracji.")

    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

    try:
        with driver.session(database=DATABASE) as session:
            records = list(session.run("""
                MATCH (c:Conversation)<-[:IN_CONVERSATION]-(p:Post)
                WITH c, p
                ORDER BY p.post_id
                WITH c, collect(coalesce(p.normalized_text, p.text, '')) AS texts
                RETURN
                    c.conversation_id AS conversation_id,
                    texts
                ORDER BY conversation_id
            """))

        ids = []
        texts = []

        for record in records:
            parts = [
                clean_text(text)
                for text in record["texts"]
                if text and text.strip()
            ]

            if not parts:
                continue

            ids.append(record["conversation_id"])
            texts.append(" ".join(parts))

        print("Konwersacje z tekstem:", len(ids))

        print("Ladowanie modelu...")
        model = SentenceTransformer(MODEL_NAME)

        print("Generowanie embeddingow...")
        embeddings = model.encode(
            texts,
            batch_size=BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        )

        print("Wyszukiwanie podobnych konwersacji...")

        edges = {}

        # Process similarities in blocks to avoid a large NxN matrix.
        for start in range(0, len(ids), 128):
            end = min(start + 128, len(ids))

            scores = embeddings[start:end] @ embeddings.T

            for local_idx, row in enumerate(scores):
                i = start + local_idx
                row[i] = -1.0

                top_indices = np.argpartition(
                    row, -TOP_K
                )[-TOP_K:]

                for j in top_indices:
                    score = float(row[j])

                    if score < THRESHOLD:
                        continue

                    a, b = sorted((ids[i], ids[j]))
                    key = (a, b)

                    edges[key] = max(
                        edges.get(key, -1.0),
                        score,
                    )

        rows = [
            {
                "source": source,
                "target": target,
                "score": round(score, 5),
            }
            for (source, target), score in edges.items()
        ]

        print("Relacje semantyczne:", len(rows))

        with driver.session(database=DATABASE) as session:
            session.run("""
                MATCH ()-[r:SIMILAR_SEMANTIC]->()
                DELETE r
            """).consume()

            for start in range(0, len(rows), 500):
                batch = rows[start:start + 500]

                session.run("""
                    UNWIND $rows AS row
                    MATCH (a:Conversation {
                        conversation_id: row.source
                    })
                    MATCH (b:Conversation {
                        conversation_id: row.target
                    })
                    MERGE (a)-[r:SIMILAR_SEMANTIC]->(b)
                    SET r.score = row.score
                """, rows=batch).consume()

        print("Zapisano relacje SIMILAR_SEMANTIC.")
        print("Gotowe.")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
