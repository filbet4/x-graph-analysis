# X Graph Analysis

Python software for the engineering thesis **Analysis of relationships between
posts on the X platform using graph methods**. The current stage implements a
complete local-data graph-analysis pipeline using fictional sample posts.

X API access, visualization, reporting, persistence, and production CLI
orchestration are not implemented yet.

## Current pipeline

```text
sample_posts.json
    -> LocalJsonPostSource
    -> PostCollection
    -> RelationshipBuilder
    -> NetworkXGraphBuilder
    -> NetworkAnalyzer
    -> optional TemporalNetworkAnalyzer
```

`LocalJsonPostSource` maps local JSON records into immutable domain entities.
`RelationshipBuilder` detects shared hashtags, replies, quotes, and reposts.
`NetworkXGraphBuilder` creates the master `networkx.MultiDiGraph`.
`NetworkAnalyzer` calculates structural metrics, centralities, PageRank,
Louvain communities, clustering/cohesion metrics, and optional
relationship-type-specific analyses. `TemporalNetworkAnalyzer` creates fixed
time-window subgraphs and delegates each window to `NetworkAnalyzer`.

Mentions exist in the domain model, but they are not currently converted into
post-to-post graph edges because a mention identifies a user rather than a
specific post.

## Architecture

- `domain`: immutable source-independent models and capability ports.
- `adapters`: local JSON ingestion and future external-source adapters.
- `preprocessing`: preprocessing boundaries; implementations are not complete.
- `graph`: relationship detection and NetworkX graph construction.
- `analysis`: structural, relationship-filtered, PageRank, Louvain, clustering,
  cohesion, and temporal analysis.
- `application`: future workflow composition boundary.
- `visualization`: future rendering boundary; not implemented.
- `reporting`: future report-generation boundary; not implemented.
- `tests`: unit, contract, and end-to-end integration tests.
- `docs`: architecture, domain, relationship, graph, and analysis decisions.

The domain layer does not depend on NetworkX or data-source details. Adapters
produce domain objects, graph construction translates them into a
`MultiDiGraph`, and analysis consumes graph representations without loading
data or detecting relationships.

## Domain and graph model

The domain includes `User`, `Post`, `Hashtag`, `Mention`, `Metrics`,
`Relationship`, `RelationshipType`, and `PostCollection`. Supported detected
post relationships are:

- `SHARED_HASHTAG`, represented as an undirected similarity relationship;
- `REPLY`, `QUOTE`, and `REPOST`, represented as directed relationships;
- `MENTION`, currently retained at user level and not converted into a post edge.

The master graph is a `networkx.MultiDiGraph`: posts are nodes, and multiple
relationship types between the same posts are preserved as parallel edges.
Shared-hashtag relationships are represented by symmetric directed edges in
the master graph. Analysis creates explicit simple directed or undirected
projections where required by algorithm semantics.

## Analysis capabilities

The current analysis layer provides:

- basic graph statistics and degree metrics;
- degree, betweenness, and closeness centrality;
- weakly and strongly connected components;
- PageRank with configurable damping factor;
- Louvain community detection with configurable resolution and seed;
- local and average clustering, transitivity, and community cohesion metrics;
- optional filtering by one or more `RelationshipType` values;
- fixed-duration temporal analysis with half-open windows.

Relationship filtering preserves every node, filters only graph edges, and
forwards the resulting graph to all existing analysis methods. Temporal
analysis uses node `created_at` timestamps, creates induced subgraphs, includes
empty windows, and delegates analysis to the same `NetworkAnalyzer`.

## Project structure

```text
src/x_graph_analysis/
  domain/         immutable models and ports
  adapters/       local JSON source adapter
  graph/          relationship detection and graph construction
  analysis/       graph and temporal analysis
  application/    future workflow composition
  preprocessing/  preprocessing boundary
  visualization/  rendering boundary
  reporting/      reporting boundary
tests/            unit, contract, and integration tests
data/             fictional sample JSON dataset
docs/             architecture and methodology notes
```

## Installation

Requires Python 3.12 or newer.

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

The project dependencies include NetworkX and its numerical PageRank backend.
Development dependencies provide pytest, Ruff, mypy, and NetworkX type stubs.

## Development checks

Run the complete test suite:

```powershell
pytest
```

Run linting, formatting validation, and type checking:

```powershell
ruff check .
ruff format --check .
mypy src
```

The current end-to-end pipeline is exercised by
`tests/test_pipeline_integration.py` using only `data/sample_posts.json`.

## Configuration and limitations

Copy `.env.example` to `.env` for local environment settings. Secrets must not
be committed. Logging is configured in
`src/x_graph_analysis/logging_config.py`.

The local JSON adapter is the only implemented data source. X API integration
is not implemented. Visualization and reporting are not implemented. The
command-line entry point remains a composition placeholder while the thesis
workflow and external data requirements are finalized.

TODO: Document the final research methodology, dataset governance, privacy
policy, reproducibility process, and evaluation criteria.
