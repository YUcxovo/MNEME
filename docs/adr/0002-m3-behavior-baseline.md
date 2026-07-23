# ADR 0002: Deterministic Behavior Model v1

- Status: accepted
- Date: 2026-07-23
- DRI: Ruiyu Jiang

## Decision

Milestone 3 introduces `behavior-v1`, a deterministic baseline that derives one user preference vector from recent paper-scoped events. It is intentionally simple and versioned so later milestones can tune or replace it without changing the `/events` contract.

The base event weights are:

| Event | Weight |
|---|---:|
| `paper_impression` | `0.1` |
| `paper_opened` | `1.0` |
| `paper_saved` | `3.0` |
| `paper_skipped` | `-1.0` |
| `paper_shared` | `4.0` |
| `question_asked` | `2.0` |
| `digest_dismissed` | `0.0` |

Only `paper_opened` uses a duration multiplier: less than 30 seconds uses `0.5`, 30 through 180 seconds uses `1.0`, more than 180 seconds uses `1.5`, and a missing duration uses `1.0`. Every signal uses exponential time decay with a 30-day half-life, and events older than 90 days do not contribute.

For each eligible event, the paper vector is the mean chunk embedding from the paper's latest observed revision, restricted to the configured embedding model. The effective signal is `base_weight * duration_multiplier * 0.5 ** (age_days / 30)`. The aggregate is the signed vector sum divided by the sum of absolute effective signals, followed by L2 normalization. Missing or incompatible paper embeddings are skipped without deleting their events. A zero or empty aggregate produces no behavior vector.

Event ingestion and preference recomputation occur in one database transaction. Client-generated event UUIDs make retries idempotent. Raw events are authoritative input; the derived vector records its embedding model and `model_version = 1`.

## Rationale

This baseline is inexpensive, explainable, deterministic, and consumes embeddings already produced by the paper pipeline. Signed feedback allows explicit skips to oppose positive interests, while absolute-weight normalization prevents negative weights from creating an unstable denominator. Recomputing from stored events avoids order-dependent online updates.

## Consequences

- No online training or external model call occurs during `/events` ingestion.
- `digest_dismissed` is retained for later notification-frequency modeling but does not affect paper similarity in v1.
- Events without a compatible paper embedding may begin contributing after a later deterministic recomputation.
- Weight tuning, alternative decay, per-user calibration, and learned models are deferred to a later milestone and require a new model version rather than an in-place semantic change.
