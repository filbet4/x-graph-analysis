# Relationship Detection

`RelationshipBuilder` transforms a `PostCollection` into a deterministic tuple
of domain `Relationship` objects. It does not construct a NetworkX graph or
perform graph analysis.

## Definitions

The shared-hashtag detector builds an inverted index from normalized hashtag
value to the posts containing that value. Candidate post pairs are generated
only from shared hashtag postings, then merged and emitted once in original
post order. This avoids comparing unrelated post pairs while preserving the
same evidence and weight semantics.

The optimization does not remove the fundamental worst case: if many posts
share one hashtag, the number of output relationships can still be quadratic.
Relationship materialization and downstream graph storage remain bounded by
that possible relationship explosion.

### Shared hashtags

Two different posts produce one `SHARED_HASHTAG` relationship when their
`Hashtag.normalized_text` sets intersect. The relationship is undirected and
has `directed=False`. The post IDs are stored in collection order, so the
reverse pair is never emitted. Its `evidence_hashtags` are the matching hashtag
objects from the first post, in their original order, and its `weight` is the
number of distinct shared normalized hashtags.

Duplicate hashtag entries within one post are counted once. Hashtag
normalization itself is outside the builder; it uses the normalized values
already present in the domain model.

### Replies, quotes, and reposts

Each direct reference creates a directed unit-weight relationship only when the
referenced post ID exists in the same collection:

| Post field | Relationship type | Direction |
| --- | --- | --- |
| `reply_to_post_id` | `REPLY` | replying post -> replied-to post |
| `quoted_post_id` | `QUOTE` | quoting post -> quoted post |
| `reposted_post_id` | `REPOST` | reposting post -> reposted post |

The builder ignores dangling references and references from a post to itself.
It does not infer relationships from text, author identity, or metrics.

### Mentions

Mentions are intentionally not converted into post-to-post relationships. The
current `Mention` model identifies a `User`, not a referenced post. Inferring
an edge from a post to all posts by that user, or selecting one post as the
target, would introduce an unapproved research rule. This remains an open
design decision and can be implemented later after the domain semantics are
defined.

## Determinism

Posts are processed in `PostCollection.posts` order. Shared-hashtag pairs are
emitted before directed reference relationships. Within each category, output
follows source-post order and the fixed reply, quote, repost field order.

TODO: Add provenance or observation timestamps to generated relationships when
the research protocol requires them.