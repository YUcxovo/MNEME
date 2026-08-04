# Android seed artifact-reuse evaluation

This protocol measures the visible Android seed-onboarding path under two paired
backend states. It does not measure Q&A, graph quality, recommendation relevance,
or complete pipeline completion time.

## Fixed pairs and timing endpoint

The three preregistered arXiv seeds are:

1. `1706.03762`
2. `2010.11929`
3. `2106.09685`

For each seed, the Android timer starts immediately before the user-facing
**Submit** click and stops after the five-paper briefing screen and its live-source
notice are both displayed. The two conditions are:

- `first`: a new disposable PostgreSQL database, a dedicated temporary Redis
  instance and queue, empty document storage, and cleared Android application data;
- `reuse`: the same backend processes and all eligible backend state are preserved,
  while Android application data is cleared again.

The contrast therefore describes seed-to-visible-briefing latency under paired
reuse-eligible system state. It does not causally isolate artifact caching from
metadata, provider, database, Redis, or operating-system reuse.

## Required invariants

Each pair uses a PostgreSQL database whose name starts with `mneme_eval_`, its own
temporary Redis server process, a unique ARQ queue, and storage namespaced by the
disposable database. The runner refuses non-local PostgreSQL, a dirty source tree,
an occupied port, multiple Android devices, or an unsafe storage identity.

After each condition, the inspector requires at least three consecutive identical
all-succeeded job fingerprints. The paired analyzer then requires:

- exactly five unique live paper identifiers in each Android result;
- identical ordered paper identifiers in `first` and `reuse`;
- a version, summary, chunks, and durable jobs for every returned paper;
- identical durable job identities and `attempt_count` values;
- identical per-paper and whole-run immutable artifact checksums;
- no queued, running, or failed durable jobs; and
- matching database, Redis instance, queue, storage, source, APK, device, and host
  provenance.

A failed condition is retained and is never rerun automatically. Text artifacts
are scanned and redacted before retention; the raw bearer token is not written to
the manifest, CSV, snapshot, or logs.

## Secure invocation

Start the local PostgreSQL service and ensure the backend provider configuration is
available through the ignored backend environment file. Then run from the repository
root with an ephemeral raw demo token:

```bash
export MNEME_EVAL_TOKEN='<ephemeral-raw-demo-token>'
export MNEME_EVAL_POSTGRES_ADMIN_URL='postgresql://<local-user>:<password>@127.0.0.1:5432/postgres'
tools/evaluation/run_android_seed_artifact_reuse.sh
```

Optional local port overrides are `MNEME_EVAL_BACKEND_PORT` and
`MNEME_EVAL_REDIS_PORT_BASE`. The three Redis instances use the base port and the
next two ports. `MNEME_EVAL_OUTPUT_ROOT` may select a different retained output
root. Never place a token or provider key in a command committed to the repository.

## Analysis boundary

The formal output contains three paired observations. The analyzer reports the
individual values plus median, minimum, maximum, and range. It does not report p95,
confidence intervals, significance tests, or population-level claims. A backend
paper may be usable at `partial` status, so the measured endpoint remains the
visible five-paper briefing; the later settled-job snapshots verify reuse
eligibility and artifact immutability outside the timed interval.
