# ADR 0003: Confidence-Calibrated Contrastive Behavior Model v2

- Status: accepted
- Date: 2026-07-27
- DRI: Ruiyu Jiang

## Context

`behavior-v1` is a deterministic signed average over recent paper embeddings. It is a useful replay baseline, but it has four limitations that matter to continuous literature recommendation. One weak interaction immediately enables the full behavior component in the recommender, repeated events on one paper can dominate the profile, positive and negative evidence can cancel into an uninterpretable near-zero vector, and a single 30-day decay scale cannot distinguish a recent topic shift from a durable interest.

The v0.1 event API and raw event table already provide an idempotent, replayable input log. Version 2 therefore changes only derived state and recommendation semantics. It does not add event types, depend on arbitrary client context, call an external model, or reinterpret silence as negative feedback.

## Decision

Mneme adopts `behavior-v2`, model version `2`, as the active derived behavior model. The v1 implementation remains frozen and callable as an evaluation baseline. Raw events remain authoritative, and a v2 profile can be rebuilt from them without mutating event history.

### Event evidence

Paper impressions are exposure records and have zero preference weight. Open, save, share, and paper-question events are positive evidence with base weights `1`, `3`, `4`, and `2`. A skip has base weight `-1`, but it is eligible only when an impression or open for the same paper occurred no more than seven days earlier. Digest dismissal remains outside the paper-interest profile because it has no paper identity.

Open duration uses a bounded continuous multiplier instead of hard tiers. For duration `d` seconds, clamped to `[0, 300]`, the multiplier is:

```text
0.5 + log(1 + d / 30) / log(11)
```

A missing duration has multiplier `1`. The transform ranges from `0.5` to `1.5`; duration can refine an open but cannot outweigh explicit save, share, or question evidence.

### Dual-timescale decay

Eligible evidence uses a mixture of recent and persistent exponential decay:

```text
decay(age) = 0.70 * 2^(-age / 14) + 0.30 * 2^(-age / 60)
```

Age is measured in days and clamped to zero for the accepted device-clock skew. Events older than 180 days do not contribute. The coefficients are fixed model parameters, not claimed optima.

### Per-paper saturation and contrastive state

For each paper, positive and negative effective weights are summed separately. Repeated evidence then receives diminishing returns:

```text
positive_support = 1 - exp(-positive_mass / 3)
negative_support = 1 - exp(-negative_mass / 1)
```

The positive and negative behavior embeddings are independently computed as support-weighted centroids over compatible latest-revision paper embeddings and then L2-normalized. A missing or near-zero channel is stored as null. Keeping the channels separate prevents cancellation from hiding contradictory evidence and lets the scorer distinguish attraction from avoidance.

### Confidence

Version 2 emits a confidence value rather than treating the first event as a fully reliable profile. Let `M` be the total saturated support over embedded papers, `D` the number of distinct embedded papers carrying non-zero support, and `Q` the fraction of eligible evidence papers with a compatible embedding. Confidence is:

```text
confidence = Q * sqrt((1 - exp(-M / 3)) * (1 - exp(-D / 3)))
```

The value is clamped to `[0, 1]`. It grows with evidence mass and paper diversity, decreases when embedding coverage is incomplete, and remains low for repeated interactions with only one paper.

### Recommendation integration

For a candidate embedding, version 2 computes positive and negative cosine similarities `p` and `n`. Its behavior affinity is:

```text
affinity = clamp(0.5 + 0.5 * (p - n), 0, 1)
```

The existing nominal behavior weight `0.35` is multiplied by profile confidence before available component weights are normalized. Explicit-topic and recency components retain weights `0.45` and `0.20`. A zero-confidence profile therefore behaves like a cold start, while a high-confidence profile can use the full behavior allocation. Version 1 replay retains its original single-vector cosine semantics.

Any change that affects ranking semantics bumps the recommendation generator identity. Fresh manual digests must match both the active preference model version and generator version. Weekly job identity must also include the active generator semantics so a completed v1 job cannot suppress v2 generation.

### Persistence and replay

`user_preferences` remains the single active preference snapshot and preserves explicit topics and followed authors. Version 2 adds a negative behavior embedding, confidence, and structured evidence summary while retaining the existing positive behavior embedding, embedding-model identity, model version, and update timestamp. Existing version 1 rows are not relabeled as version 2. A dedicated replay command recomputes the active profile from raw events under the same per-user lock and transaction boundary as event ingestion.

## Invariants

- Event UUID idempotency and the frozen `/events` request contract do not change.
- Event insertion and profile recomputation remain one transaction.
- The user row is locked before the preference row, matching other preference writers.
- Latest paper revisions and the exact configured embedding model remain the only profile inputs.
- Missing embeddings never delete raw events and reduce reported coverage.
- The same events, embeddings, configuration, and reference time produce the same profile.
- Explicit preferences are never overwritten by behavior recomputation.
- Scores remain bounded, ranking keeps a stable UUID tie-break, and every digest entry retains a reason.

## Consequences

The model is transparent and cheap enough to run synchronously after an event batch. Its controlled evaluation can isolate recency, saturation, exposure gating, contrastive negative evidence, and confidence gating without external APIs. It is still a hand-designed content-space model: controlled replay can validate its mechanisms but cannot prove long-term user benefit or optimal parameters. Such claims require longitudinal user data and remain outside the bounded evaluation.
