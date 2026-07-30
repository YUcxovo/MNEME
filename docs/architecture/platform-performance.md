# Platform Performance Audit

This document records the bounded query and connection decisions used for backend hardening. It distinguishes structural query evidence from environment-sensitive timing evidence; no latency improvement is claimed without a reproducible PostgreSQL plan comparison.

## Verified access paths

| Path | Bound and ordering | Supporting index or mechanism |
|---|---|---|
| Paper list | `limit <= 50`, descending `(published_at, id)` keyset | `ix_papers_published_id` |
| Category paper list | Same keyset under one `primary_category` | `ix_papers_category_published` |
| User digest list | `limit <= 50`, one-user descending `(generated_at, id)` keyset | `ix_digests_user_generated` |
| Dispatch recovery | Queued state, lease timestamp, then creation order | `ix_pipeline_jobs_dispatchable` |
| Citation expansion | Bounded depth/node request in both edge directions | internal source/target partial index plus `ix_citations_target_paper_id` |
| Induced graph edges | Both endpoints restricted to the bounded node set | internal source/target partial index |

Paper and digest repositories fetch `limit + 1` rows to derive an opaque continuation cursor and never use offset pagination. Unit tests lock the SQL ordering and predicates. PostgreSQL integration coverage walks tied-timestamp digest keys across pages and rejects gaps, duplicates, and cross-user leakage. API validation limits both public page sizes to 1--50.

## Connection capacity

API, worker, scheduler, and standalone CLI processes all construct `Database` through the same settings-backed factory. Pool size, overflow, checkout timeout, recycle interval, and pre-ping are explicit. `pool_size + max_overflow` is a per-process maximum, so deployment capacity is the configured maximum multiplied by the number of backend processes.

## Operations-report queries

The operations snapshot intentionally combines selective reads with global aggregates. The current status/stage and dispatch-lease queries use existing job indexes. Global paper-status, latest-parse-quality, job-creation, and digest-generation aggregates may correctly use sequential scans as the dataset grows; adding low-selectivity indexes without a measured plan would increase write and vacuum cost without established benefit.

The bounded recent-failure query filters on `status = 'failed'`, ranges and orders by `finished_at`, then returns at most 100 rows. A partial `(finished_at, id)` index is the only current migration candidate. It is deliberately not added in this audit because the local environment has no configured PostgreSQL dataset on which to compare identical before/after plans. This is an evidence gate, not a claim that the candidate is ineffective.

## Measurement gate for a new index

Before adding an index, use an isolated disposable database migrated to `head`, populate a fixed representative workload, run `ANALYZE`, and capture `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` before and after the candidate. Keep PostgreSQL planner defaults, workload rows, query parameters, warm-up count, and repetitions identical. Retain PostgreSQL/pgvector versions, row counts, raw plans, timing samples, and sanitized configuration; do not retain credentials, hostnames, or personal paths.

CI verifies result correctness, cursor completeness, user isolation, query bounds, migration consistency, and index declarations. It does not enforce wall-clock thresholds or a specific planner node because shared-runner timing and small-table plans are not stable performance evidence. A migration is accepted only when the retained same-workload comparison reduces relevant rows scanned or removes the bounded-result sort without materially harming writes.
