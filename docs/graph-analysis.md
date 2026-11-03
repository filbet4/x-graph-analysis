# Graph Analysis

`NetworkAnalyzer` calculates reusable structural metrics from the existing
`networkx.MultiDiGraph`. It returns immutable dataclass results and never loads
data, detects relationships, mutates the master graph, or performs
visualization or reporting.

## Basic statistics

- `node_count`: number of post nodes.
- `edge_count`: number of master `MultiDiGraph` edges, including both arcs used
  to represent one shared-hashtag relationship.
- `density`: NetworkX directed density, `m / (n * (n - 1))`; parallel edges are
  included in `m`.
- `isolated_node_count`: nodes with no incident master-graph edges.

## Per-node metrics

`NodeMetrics` is returned in graph node insertion order and contains:

- degree, in-degree, and out-degree, counted directly on the master
  `MultiDiGraph`, so parallel relationship edges count separately;
- degree centrality, normalized by `n - 1` using NetworkX's multigraph degree;
- in-degree and out-degree centrality, using the same `n - 1` denominator;
- betweenness and closeness centrality from the analysis projection described
  below.

For a one-node graph, all normalized degree and centrality values are `0.0`.

## Components

Weakly and strongly connected components are calculated on the directed simple
projection. Results and per-node component IDs are ordered deterministically by
first appearance in the master graph. Weak components ignore arc direction;
strong components require mutual directed reachability.

## MultiDiGraph projection

NetworkX path-based and component algorithms have ambiguous semantics when
parallel edges represent different relationship types. The analyzer therefore
creates a private `DiGraph` projection:

1. copy every node;
2. add one unweighted directed arc for each ordered source-target pair in the
   master graph;
3. collapse parallel edges;
4. preserve both directions of a shared-hashtag relationship;
5. ignore edge weights because shared-hashtag weight counts hashtags rather than
   traversal distance.

The projection is used only for weak components, strong components,
betweenness, and closeness. The master `MultiDiGraph` is never changed.
Closeness retains NetworkX's directed convention: it measures incoming
reachability by default. Betweenness uses normalized unweighted shortest paths.

## Interpretation limits

Degree metrics describe observed relationship multiplicity in the master graph,
while path metrics describe reachability in the collapsed projection. These
values should not be compared as if they used identical edge semantics. The
choice to ignore relationship weights for paths is a methodological default and
should be revisited if a future study defines interaction cost or distance.

TODO: Decide whether directed closeness should use incoming, outgoing, or both
reachability for the thesis research questions.

## PageRank

`PageRankScore` gives every post a score representing its structural importance
under a random-surfer model. A post receives more rank when it is linked by
other posts that themselves carry rank. Scores are normalized to sum to one for
non-empty graphs.

PageRank uses the same private simple directed projection described above:
parallel edges collapse into one directed arc, both arcs of a symmetric
shared-hashtag relationship remain, and `Relationship.weight` is ignored. No
relationship-type-specific weights are introduced. This makes a reply, quote,
repost, and shared-hashtag arc equal for this initial analysis.

The damping factor `alpha` defaults to `0.85` and is configurable when creating
`NetworkAnalyzer`. It represents the probability that the random surfer follows
an outgoing link rather than teleporting to a uniformly selected post. Valid
values are finite real numbers satisfying `0 < alpha <= 1`.

PageRank on this post graph is structural rather than a measure of content
quality, truth, influence, or author importance. It is also sensitive to the
chosen relationship set, the symmetric encoding of shared hashtags, dangling
nodes, and the decision to treat all relationship types equally. The effect of
these choices should be evaluated against the thesis research questions.

TODO: Determine whether a future methodology should use separate projections
or relationship-type weights for PageRank.

## Community detection

`CommunityDetectionResult` identifies groups of posts with comparatively dense
internal connections under the Louvain method. It provides immutable community
records, member tuples, sizes, a total community count, and a membership record
for every graph node.

### Louvain projection

Louvain is applied to a private simple undirected `Graph` projection, separate
from the directed projection used for components, centralities, and PageRank.
The projection:

1. copies every master-graph node, including isolated nodes;
2. adds one undirected edge for each connected pair of posts;
3. collapses parallel edges;
4. collapses opposite directed edges into the same undirected edge; and
5. ignores relationship weights and relationship types.

The projection therefore represents only whether posts are connected. It does
not treat a shared hashtag as stronger than a reply, quote, or repost, and it
does not count the two symmetric master arcs as two community edges.

### Configuration and deterministic IDs

`NetworkAnalyzer` uses NetworkX's Louvain implementation with a default
`resolution=1.0` and fixed `seed=42`. The resolution controls the community
scale: larger values generally favor more, smaller communities, while smaller
values generally favor fewer, larger communities. The seed controls randomized
tie-breaking and ordering inside Louvain.

NetworkX's raw communities are sets, so the analyzer sorts each member tuple by
master graph insertion order and then sorts communities by the first member's
position. Integer community IDs are assigned only after that ordering. This
keeps IDs reproducible without depending on arbitrary set iteration order.

### Interpretation limits

Connected components and communities answer different questions. A connected
component is a hard reachability boundary: no path crosses between components.
Louvain communities are an optimization result inside the projected graph and
may divide one connected component into several communities. They can also be
sensitive to resolution, seed, graph density, and ties in the modularity
optimization.

Because this initial projection ignores relationship types and weights, the
communities describe untyped structural proximity only. They should not yet be
interpreted as topical, semantic, user, or influence communities. Isolated
posts are retained as singleton communities because the projection includes
all master nodes.

TODO: Evaluate whether a research-valid community model should distinguish
interaction types or use weighted relationships after the baseline is tested.

## Clustering and graph cohesion

Clustering metrics use the same private simple undirected projection as
community detection. Every master node is copied, every connected post pair
creates one unweighted undirected edge, parallel edges collapse, opposite
directed edges collapse, and relationship types and weights are ignored. The
master `MultiDiGraph` is never changed.

### Local clustering coefficient

`ClusteringCoefficient` contains one coefficient per node. For a node with
degree $k$, the coefficient is the fraction of the possible neighbor-neighbor
connections that actually exist:

$$C_v = \frac{2T_v}{k_v(k_v - 1)}$$

where $T_v$ is the number of triangles containing node $v$. Isolated nodes and
nodes with degree less than two have coefficient `0.0`.

### Average clustering

`average_clustering` is the arithmetic mean of local coefficients over all
nodes in the undirected projection. This includes isolated nodes as zeroes.
For an empty graph it is explicitly defined as `0.0`.

### Transitivity

`transitivity` is the global fraction of connected triples that are closed by
an edge, calculated by NetworkX on the undirected projection. It weights nodes
by their number of triples rather than giving every node equal influence. For
an empty graph, a graph with no edges, or any graph with no valid connected
triplets, it is defined as `0.0`.

Average clustering and transitivity are therefore different: average clustering
is a node-level average, while transitivity is a global triadic ratio. They can
produce different values on heterogeneous graphs even when computed from the
same projection.

### Community structural metrics

`CommunityStructuralMetrics` is returned for each already-detected Louvain
community. It contains:

- `node_count`: number of community members;
- `internal_edge_count`: number of edges in the community-induced undirected
  projection;
- `internal_density`: internal edges divided by the possible undirected edges,
  with singleton communities defined as `0.0`;
- `average_clustering`: mean local coefficient for the community's members.

The community average is computed from a community-induced subgraph, not from
the global local clustering coefficients. Thus external neighbors cannot lower
or raise the reported internal cohesion of a community. Community metrics
reuse the existing Louvain result and do not run community detection again.
Community and node outputs retain deterministic ordering.

These cohesion metrics are structural only. Because the projection ignores
relationship types and weights, they do not distinguish replies, quotes,
reposts, mentions, or shared hashtags, and they should not yet be interpreted
as semantic cohesion or interaction strength.

TODO: Establish whether future thesis experiments need type-aware or weighted
cohesion metrics after the unweighted baseline has been evaluated.

## Domain invariants

The domain model rejects clearly invalid states before graph construction:

- `User.user_id` and `User.username` must be non-empty;
- `Post.post_id` must be non-empty and `published_at` must be timezone-aware;
- `Metrics` counts must be non-negative;
- `Relationship` endpoints must be non-empty and distinct, and `weight` must
  be positive;
- `RelationshipType.SHARED_HASHTAG` must be undirected, while the other
  currently supported relationship types must be directed;
- `PostCollection` post IDs must be unique.

These checks prevent duplicate NetworkX nodes and contradictory relationship
states from entering later layers.

## Relationship-specific analysis

`NetworkAnalyzer.analyze(graph)` preserves the existing combined-graph
behavior. Callers can instead pass a collection of domain `RelationshipType`
values:

```python
analyzer.analyze(
    graph,
    relationship_types={RelationshipType.REPLY, RelationshipType.QUOTE},
)
```

The analyzer first creates a private filtered `MultiDiGraph`. It copies every
master node and keeps only edges whose `relationship_type` attribute is in the
selected enum set. Edge keys, parallel edges, node attributes, and edge
attributes are preserved. The master graph and domain objects are never
modified, and no relationships are detected or rebuilt.

The result metadata distinguishes the two modes:

- `relationship_types=None` means no filter was supplied, so all master edges
  participate;
- `relationship_types=()` means an explicit empty selection, so all nodes are
  retained but no edges participate;
- an explicit non-empty selection is stored as a deterministic tuple sorted by
  enum value.

All existing projections then operate on the filtered graph. The directed
simple projection drives components, betweenness, closeness, and PageRank. The
undirected simple projection drives Louvain, clustering, transitivity, and
community structural metrics. Thus symmetric shared-hashtag arcs remain
opposite directed arcs in directed analyses, but collapse to one undirected
connection in undirected analyses. Parallel selected edges remain in the
filtered master graph and count for direct degree metrics, but collapse in
simple projections as before.

Filtering creates relationship-specific structural views, not independent
datasets. Comparing a reply-only graph with a quote-only graph compares
different topologies and potentially different isolated-node populations, even
though node identity is preserved. Centralities, PageRank, communities, and
cohesion should therefore be interpreted relative to the selected relationship
set; their values are not automatically comparable across filters.

TODO: Define a thesis-specific protocol for comparing metrics across
relationship-type selections, including minimum edge and component thresholds.

## Temporal analysis

`TemporalNetworkAnalyzer` provides fixed-window time series over the existing
graph-analysis engine. It uses each node's `created_at` attribute as the post
timestamp, partitions posts chronologically, creates an induced temporal
subgraph, and delegates that subgraph to `NetworkAnalyzer`. It does not
duplicate structural metrics, PageRank, Louvain, clustering, or relationship
filtering logic.

### Fixed windows

Windows have configurable positive `datetime.timedelta` duration and use
half-open intervals `[start, end)`. A timestamp exactly equal to a window's
`end` belongs to the next window's `start`. The effective range is derived from
the minimum and maximum post timestamps when no explicit range is supplied. The
final derived window ends at the next window boundary, while an explicit range
may produce a shorter final partial window.

All timestamps, including explicit boundaries, must be timezone-aware. Missing,
invalid, or naive node timestamps raise `TemporalAnalysisError`. Explicit
ranges require `start < end`, compatible timezone-aware values, and all post
timestamps must fall inside `[start, end)`.

Empty windows are included. This keeps the result structurally consistent for
time-series consumers and makes gaps visible rather than silently removing
them. An empty graph without an explicit range has no meaningful temporal range
and therefore returns no windows. An empty graph with an explicit range still
returns empty windows for the requested range.

### Induced temporal subgraphs

Each window includes nodes whose timestamps fall inside its interval. An edge is
included only when both endpoint nodes belong to that window. This makes every
window an induced `MultiDiGraph`: edge keys, parallel edges, node attributes,
and edge attributes are preserved. Cross-window relationships are excluded
from both windows; no new cross-window edge is inferred.

Each induced graph is passed to the existing `NetworkAnalyzer`, optionally with
the same `relationship_types` filter supplied by the caller. Consequently,
filtered temporal analysis retains the same `None` versus explicit selection
metadata and projection semantics as non-temporal analysis.

### Limitations

Fixed non-overlapping windows make changes easier to compare but can hide events
that straddle a boundary and make results sensitive to the chosen origin and
duration. They do not provide sliding windows, dynamic community tracking,
trend interpretation, or anomaly detection. A post's node timestamp determines
window membership; relationships are not modeled as events with independent
timestamps. Comparisons across windows should account for changing node counts,
edge counts, isolated posts, and partial final windows.

TODO: Evaluate alternative window origins and durations against the thesis
research questions before interpreting temporal metric trends.
