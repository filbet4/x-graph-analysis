# Graph Construction

`NetworkXGraphBuilder` translates a `PostCollection` and an already detected
sequence of `Relationship` objects into a `networkx.MultiDiGraph`. It does not
detect relationships, infer edges, or run graph algorithms.

## Why `MultiDiGraph`

`MultiDiGraph` is the primary representation because multiple relationship
types can exist between the same two posts. For example, two posts may have a
reply relationship and also share hashtags. A simple `DiGraph` would overwrite
one edge's metadata; a multigraph preserves both relationships as parallel
edges.

The directed container also supports the directed interaction relationships
(`REPLY`, `QUOTE`, and `REPOST`) directly. The original semantics of every edge
are retained in the `directed` attribute.

## Nodes

Each post becomes exactly one node, identified by `Post.post_id`. The builder
stores selected scalar and immutable metadata as node attributes:

- `author_id`
- `username`
- `created_at` from `Post.published_at`
- normalized hashtag names in `hashtags`
- post text in `text`

The complete `Post` object is not copied into the node attributes. The graph
therefore remains a representation of the domain data rather than a second
domain model.

## Edges

The builder consumes existing relationships and preserves their metadata:

- `relationship_type`
- `weight`
- `evidence_hashtags`
- `directed`
- `observed_at`

`REPLY`, `QUOTE`, and `REPOST` produce one edge from source post to target
post. A `SHARED_HASHTAG` relationship is conceptually undirected, so it is
represented in the `MultiDiGraph` by two symmetric edges. Both edges receive
identical relationship attributes, including `directed=False`.

The builder does not create `MENTION` edges. The current domain model points a
mention to a user rather than to a post, so the post-to-post semantics remain
an open design decision documented in [relationship-detection.md](relationship-detection.md).

## Responsibility boundary

`RelationshipBuilder` detects relationships from posts. `NetworkXGraphBuilder`
only translates those domain relationships into NetworkX nodes and edges.
The existing graph analysis components consume the resulting `MultiDiGraph`
without depending on the data-source adapter or repeating detection rules.

TODO: Decide whether graph node text should be omitted or externalized for
privacy and memory constraints before large-scale data collection.