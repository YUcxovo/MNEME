# Behavior Model Evaluation Protocol

## Objective and evidence boundary

The evaluation tests whether the frozen `behavior-v2` mechanisms improve controlled future-paper ranking and adaptation relative to declared baselines. It uses synthetic, deterministic event traces with known latent relevance labels. These traces are not presented as observed user behavior and cannot establish satisfaction, productivity, or long-term personalization benefit.

The implementation and final measurements are separate commits. This protocol, fixture schema, model parameters, metric definitions, and random seed must be frozen before the recorded run. Exploratory runs write to `/tmp`; the recorded runner refuses a dirty worktree and retains raw case results, environment metadata, exact configuration, fixture hash, and source identity under `docs/evaluation/behavior/`.

## Evaluation questions

1. Does v2 rank known relevant candidates above distractors more consistently than v1 under stable-interest, interest-shift, exposed-negative, and contradictory-feedback traces?
2. Does confidence gating reduce overreaction to sparse or single-paper history?
3. Do exposure gating and per-paper saturation prevent unexposed negative events and repeated same-paper events from dominating the profile?
4. Are profile construction, ranking, replay, and result serialization deterministic?

## Compared systems

The primary comparison contains:

- `recency-only`: the candidate recency component without explicit or behavioral state;
- `explicit-recency`: explicit topic matching plus recency;
- `behavior-v1`: the frozen signed, single-timescale v1 profile with the deployed scorer;
- `behavior-v2`: the complete model from ADR 0003.

The essential v2 ablations are:

- `v2-single-timescale`: replaces the decay mixture with one 30-day half-life;
- `v2-no-saturation`: uses unsaturated per-paper evidence mass;
- `v2-no-exposure-gate`: accepts every skip as negative evidence;
- `v2-no-negative-channel`: omits the separate negative profile;
- `v2-no-confidence-gate`: forces behavior confidence to one when a profile exists.

Ablations diagnose mechanisms; they are not additional headline models. Parameters may not be selected after inspecting final test results. Any subsequent parameter change creates a new fixture or model version and a separate run.

## Controlled traces

The versioned fixture contains small-dimensional artificial paper embeddings, stable UUIDs, UTC timestamps, explicit topics, candidate metadata, event histories, and graded relevance judgments. Scenario families cover cold start, stable positive interest, recent topic shift, exposed negative feedback, unexposed skip, repeated same-paper engagement, contradictory feedback, missing embedding coverage, and duplicate replay.

Each scenario declares only inputs and relevance labels. It does not encode a required winner or minimum improvement. Paired before/after scenarios share a `pair_id` so adaptation and correction deltas are computed from the same candidate set.

## Metrics

Primary ranking metrics are nDCG at 5, Recall at 5, and reciprocal rank. Metrics are reported only where the fixture defines an eligible relevant item; undefined values remain null and are excluded from aggregates rather than converted to zero.

Mechanism-specific metrics are target rank and score deltas for interest shifts and exposed skips, maximum score change under duplicate replay, profile confidence, embedding coverage, and candidate-list intra-list diversity. The harness also records finite-score, score-bound, deterministic-replay, exposure-gate, and duplicate-idempotency invariants.

Model comparisons use paired per-scenario differences. The recorded analysis reports the number of applicable scenarios, mean and median differences, and a fixed-seed percentile bootstrap 95 percent interval. It does not infer population-level user effects from synthetic cases and does not use a p-value threshold as a success gate.

## Reproducibility artifacts

The recorded run produces:

```text
docs/evaluation/behavior/
|-- README.md
|-- fixtures/
|   `-- behavior_controlled_v1.json
|-- raw/
|   |-- case_results.jsonl
|   |-- environment.json
|   `-- run_manifest.json
|-- summary.csv
|-- summary.json
`-- figures/
    |-- ranking_comparison.png
    `-- mechanism_deltas.png
```

The manifest records the fixture and lockfile SHA-256 values, exact source identity, clean-tree state, Python and uv versions, platform and CPU summary, UTC reference time, fixed seed, complete model configurations, metric definitions, rounding policy, and invoked command. It excludes tokens, secrets, real user identifiers, private paths, and raw personal behavior.

## Claim gate

Unit and integration tests establish deterministic implementation and transaction invariants. Controlled replay establishes behavior on declared artificial traces. Neither evidence class proves that users prefer the recommendations. Thesis claims must remain within the measured ranking, adaptation, exposure, saturation, confidence, and reproducibility properties unless a separately approved longitudinal study supplies stronger evidence.

