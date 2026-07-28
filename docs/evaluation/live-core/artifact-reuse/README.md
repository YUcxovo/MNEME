# Android live-core acceptance evaluation

This evaluation supplements the controlled Android E4 measurements with a
real-backend product path. It is deliberately separate from the E4 performance
suite: the purpose is to establish that the implemented Android client can
carry one fixed seed and one fixed free-form question through the production
client contracts, not to evaluate retrieval, answer, recommendation, or graph
algorithm quality.

## Research question and scope

The bounded question is:

> Can the Android client complete the implemented seed-to-reading path against
> a real Mneme backend while preserving live/cached provenance and the public
> API contracts?

The retained path covers:

1. submit one preregistered arXiv seed and receive exactly five papers;
2. restore the resulting briefing through the Android cache;
3. open one returned paper and its stored summary;
4. submit one preregistered free-form question and receive an answer;
5. open the paper source through the UI callback;
6. load a multi-node citation graph centred on the selected briefing paper;
7. select a different graph node; and
8. use Open Paper to reach that neighbour's normal paper-detail path.

One Compose trace exercises the visible UI. Five additional repetitions use
the same production Android repository, Retrofit mapping, Room cache, and live
backend, starting from the live briefing created by the UI trace. Seed
initialisation is performed once so the repeated client path does not repeatedly
query the external citation provider. The repetitions use the same paper and
question by design. They measure path reliability under durable artifact and
provider-cache reuse; they are not independent answer-quality samples.

An optional multi-seed matrix runs additional arXiv seeds through the production
Android repository. Each row independently requests a five-paper briefing, loads
the first paper's depth-two graph, selects a non-centre node, and loads that
neighbour through the ordinary paper path. This matrix checks that the client
contract is not tied to the preregistered Transformer seed. It does not score
paper relevance or graph quality.

## Fixed inputs and success criteria

The default seed is `1706.03762`. The fixed question is:

> What problem does this paper address, and what method does it propose?

The runner records the exact values in `raw/run_manifest.json`. A stage passes
only when:

- the seed response contains exactly five papers and is labelled live;
- each repeated live briefing contains the same five-paper result;
- cache restore contains the same five-paper briefing and is labelled cached;
- paper detail contains non-empty abstract and summary content plus an arXiv
  source URL;
- Q&A returns a non-empty answer with live origin;
- the graph contains its requested centre, at least one neighbour and one edge,
  stays within 50 nodes, and is labelled live;
- neighbour selection remains visible in the graph screen; and
- Open Paper returns the selected neighbour through the ordinary paper-detail
  path.

Source count and source-match status are retained as descriptive Q&A outputs.
When a source is present, the UI trace also exercises its callback; source
availability is not used to redefine whether the client completed the question
request. An empty answer, a one-node graph, a graph without an edge, a failed
selection, or a failed Open Paper transition remains a failed required stage.

## Run

Start a backend and worker that are visible to one Android emulator. Then set:

```bash
export MNEME_LIVE_CORE_BASE_URL=http://10.0.2.2:8000/v1/
export MNEME_LIVE_CORE_TOKEN='<ephemeral raw token>'
export MNEME_LIVE_CORE_SEED=1706.03762
export MNEME_LIVE_CORE_MATRIX_SEEDS='2010.11929,2106.09685'
export MNEME_LIVE_CORE_QUESTION='What problem does this paper address, and what method does it propose?'
tools/evaluation/run_android_live_core_acceptance.sh
uv run tools/evaluation/analyze_android_live_core.py
```

The raw token is passed to Android instrumentation and is never retained. The
runner refuses a dirty tracked worktree, requires exactly one ready device, and
records the repository revision, device environment, fixed inputs, and
non-secret AI configuration. Its exit trap pulls partial artifacts even if a
live stage fails. The runner builds the test APK without an embedded demo token,
so ordinary application background scheduling cannot interfere with the
instrumented path. The live token is supplied only to the repository constructed
inside the test.

## Evidence and interpretation

`raw/live_core_path.csv` is the direct stage log.
`raw/live_seed_matrix.csv` contains one independently initialized client path per
additional seed.
`raw/environment.json` and `raw/run_manifest.json` bind it to the device,
revision, input, and model configuration. The retained screenshots show the
live briefing, paper, Q&A result, graph, and selected-neighbour state. `summary.csv`,
`summary.json`, and `figures/live_core_acceptance.*` are generated from the raw
CSV.

The single UI trace is acceptance evidence, not a latency distribution. The
five repository repetitions support only the observed path success rate. Later
iterations may reuse PostgreSQL artifacts, Redis completions, and local
embeddings, so their timing distribution must not be described as five cold
first-run measurements.

## Recorded run

The retained run completed all 38 fixed-path stages successfully. The visible
Compose path reached a six-node, five-edge graph, selected a different node,
and opened that paper. Each of the six repeated repository stages succeeded in
all five repetitions.

Both additional seeds also completed their required client paths. Seed
`2010.11929` returned five papers and a six-node, five-edge graph in
48.058 seconds. Seed `2106.09685` returned five papers and a seven-node,
six-edge graph in 46.598 seconds. Graph loading and opening a neighbour took
less than 40 milliseconds in both rows; most elapsed time was the synchronous
first-time preparation of the five-paper briefing. These are two acceptance
observations, not a population latency estimate.

This evaluation does not assess whether the selected five papers are relevant,
whether the generated answer is scientifically correct, whether any returned
source semantically entails the claim, whether the graph neighbourhood is
useful, or whether users find the interaction usable. Those questions require
separate recommendation, AI-quality, graph-algorithm, or participant protocols.
