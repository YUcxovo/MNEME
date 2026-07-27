# Controlled Behavior Evaluation

This directory defines the reproducible evaluation for Mneme's confidence-calibrated contrastive behavior model. The fixture is deterministic and synthetic: it tests ranking and adaptation mechanisms under declared geometric scenarios, not whether real researchers are satisfied or more productive.

The governing design sources are:

- [`../../adr/0003-behavior-v2.md`](../../adr/0003-behavior-v2.md) for the production algorithm and invariants;
- [`../../architecture/behavior-evaluation.md`](../../architecture/behavior-evaluation.md) for the preregistered comparison and evidence boundary;
- [`fixtures/behavior_controlled_v1.json`](fixtures/behavior_controlled_v1.json) for the frozen inputs, relevance labels, seed, bootstrap count, and rounding policy.

## Compared systems

The four headline systems are `recency-only`, `explicit-recency`, the frozen `behavior-v1` replay baseline, and the complete `behavior-v2` model. Five diagnostic ablations independently remove the dual timescale, per-paper saturation, exposure gate, negative channel, or confidence gate. Every system calls the production aggregation and recommendation code; the harness does not maintain a second scoring formula.

The controlled fixture covers nine scenario families: cold start, stable positive interest, recent interest shift, exposed negative feedback, unexposed skip, repeated same-paper evidence, contradictory feedback, incomplete embedding coverage, and duplicate replay. History papers and ranking candidates have stable UUIDs and artificial four-dimensional vectors. No raw personal behavior, external API call, database, provider model, or production credential is involved.

A separate environment-sensitive benchmark exercises the same production aggregation and ranking functions with 1536-dimensional vectors. It freezes three scales from 64 events and 50 candidates through 4096 events and 1000 candidates, performs five warm-ups and 30 measured repetitions, and retains raw timing samples with descriptive median and p95 summaries. It measures in-process Python computation only, not database, network, provider, or Android latency.

The current Android producer emits impressions, opens, and paper-scoped questions. Save, skip, share, and dwell-time cases therefore validate backend contract semantics and stress mechanisms; they are not evidence that those signals have already been observed from the current mobile client.

## Metrics and direction conventions

The primary ranking metrics are graded nDCG@5, Recall@5, and reciprocal rank. A metric is `null` when the case has no eligible relevant candidate, and null values are excluded from the applicable denominator rather than replaced with zero. Top-five intra-list diversity is also retained as a descriptive diagnostic.

All model comparisons are paired by scenario. The summary reports `behavior-v2 - comparator`, so a positive ranking-metric difference favors v2. The fixed-seed percentile interval resamples scenario-level paired differences 10,000 times and is descriptive only; it is not interpreted as population uncertainty over real researchers.

For paired mechanism traces:

- `target_rank_delta = after rank - before rank`; a negative value means the target moved upward, while a positive value means it was suppressed;
- `target_score_delta = after score - before score`;
- duplicate replay reports the maximum absolute candidate-score difference and requires exact zero.

## Development verification

Run the fast deterministic contracts from `backend/`:

```bash
uv run pytest \
  tests/test_behavior_v2_model.py \
  tests/test_behavior_evaluation_fixtures.py \
  tests/test_behavior_evaluation_metrics.py \
  tests/test_behavior_evaluation_harness.py \
  tests/test_behavior_evaluation_analysis.py \
  tests/test_behavior_evaluation_reporting.py \
  tests/test_behavior_evaluation_provenance.py \
  tests/test_evaluate_behavior_cli.py \
  -m base
```

An exploratory run writes outside the repository and may use a dirty tree:

```bash
cd backend
uv run python -m mneme.cli.evaluate_behavior \
  --output /tmp/mneme-behavior-evaluation

cd ..
uv run --script tools/evaluation/plot_behavior_evaluation.py \
  --evaluation-dir /tmp/mneme-behavior-evaluation
```

Exploratory artifacts must not be cited as the retained thesis evidence.

## Recorded run

The formal command is intentionally manual:

```bash
cd MNEME
tools/evaluation/run_behavior_evaluation.sh
```

Recorded mode refuses a dirty Git worktree before creating or overwriting any result. It writes:

```text
docs/evaluation/behavior/
|-- fixtures/behavior_controlled_v1.json
|-- raw/
|   |-- case_results.jsonl
|   |-- environment.json
|   `-- run_manifest.json
|-- performance.json
|-- summary.csv
|-- summary.json
`-- figures/
    |-- mechanism_deltas.pdf
    |-- mechanism_deltas.png
    |-- performance_scaling.pdf
    |-- performance_scaling.png
    |-- ranking_comparison.pdf
    `-- ranking_comparison.png
```

The manifest records the exact source revision, branch, clean-tree state, fixture and lockfile hashes, Python and uv versions, platform summary, fixed analysis settings, complete model configurations, reference time, and a sanitized command. It does not retain environment variables, tokens, raw user identifiers, absolute personal paths, or paper/provider content.

## Interpretation boundary

Unit and integration tests support claims about deterministic implementation, transaction boundaries, idempotency, and bounded scores. Controlled replay can support claims about the declared synthetic ranking, adaptation, saturation, exposure, contrastive, confidence, and reproducibility properties. The performance benchmark supports only environment-specific statements about in-process aggregation and ranking latency at its declared scales. None of these evidence classes establishes preference-inference accuracy for real researchers, longitudinal usefulness, engagement improvement, causal benefit, fairness, or superiority to trained industrial recommender systems. Stronger claims require a separately designed and approved user study.
