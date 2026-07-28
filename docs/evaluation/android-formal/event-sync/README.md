# Formal Android Event-Synchronization Measurement

This directory is reserved for the small formal measurement of Android event-queue
durability and backend idempotency. It replaces neither the earlier E4 pilot data nor any
backend recommendation evaluation. The unit of repetition is one independent batch of
three newly generated behavioral-event UUIDs.

## Measured sequence

Each of the ten formal batches executes the same five stages in order:

1. **Queue write:** write three events to the file-backed production Room database and
   verify that all three UUIDs are pending.
2. **Room reopen:** close and reopen that database and verify that the same pending UUIDs
   remain.
3. **HTTP 503 recovery:** submit the queue to a controlled `MockWebServer` response,
   verify the `/v1/events` request body, and verify that all events remain pending with one
   recorded attempt.
4. **Live upload:** send the same queue to the isolated FastAPI/PostgreSQL backend and
   require `accepted=3`, `duplicates=0`, and three locally synced events.
5. **Duplicate replay:** create a new file-backed database with the same UUIDs, submit it
   to the same backend, and require `accepted=0`, `duplicates=3`, and three locally synced
   events.

Only the operation named by each row is timed. Validation, database preparation, and
artifact collection are outside that row's timing boundary. The controlled 503 stage uses
real HTTP through the Android network client; the two final stages use the explicitly
configured live test backend.

## Preconditions

- Use a dedicated test backend, database, Redis namespace, and test user. The run writes
  30 unique events and must not target shared or production data.
- The test user must be authorized and the backend must contain at least one paper. Set
  `MNEME_EVENT_SYNC_PAPER_ID` to a stable paper UUID when one is available.
- Start exactly one Android emulator. Physical devices, multiple targets, and offline
  emulator entries are rejected. Use a disposable measurement emulator: the runner
  force-stops the app and clears all `com.mneme.app` application data before acquisition.
- Commit the measurement code first. The runner rejects staged, modified, and untracked
  files so that every APK is tied to a clean revision. At completion, it permits new files
  only inside that run's unique artifact directory; any changed tracked file, staged
  change, new file elsewhere, or changed source hash invalidates the run.
- JDK 17 and the Android SDK must be available. The runner passes an explicitly blank
  build-time authentication value, preventing background work from consuming the measured
  Room queue. The live credential is supplied only as an instrumentation argument and is
  redacted from the saved transcript.

## Formal acquisition

The following environment variables are mandatory. Do not put the credential in this
README, a shell script, a manifest, or a committed environment file.

```bash
export ANDROID_SDK_ROOT="$HOME/Android/Sdk"
export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
export MNEME_EVENT_SYNC_BASE_URL="http://10.0.2.2:8000/v1/"
export MNEME_EVENT_SYNC_TOKEN="<test-user-token>"
export MNEME_EVENT_SYNC_PAPER_ID="<stable-paper-uuid>"
export MNEME_EVENT_SYNC_ISOLATED_BACKEND_ACK="isolated-test-backend"

tools/evaluation/run_android_formal_event_sync.sh
```

Formal mode is fixed at ten batches. It builds and installs one blank-authentication app
APK and one test APK, then issues exactly one instrumentation invocation. It never retries
the experiment. Before removing old measurement output or starting instrumentation, it
requires both a successful `am force-stop` command and an exact `Success` response from
`pm clear com.mneme.app`. The manifest records these fresh-app-data guards, and the analyzer
rejects a run without them. On instrumentation failure, the failed transcript, any partial
CSV, and a failure manifest are retained under:

```text
docs/evaluation/android-formal/event-sync/raw/formal-<UTC>-<revision>/
```

Diagnose a failed run from that directory. If a new acquisition is justified, retain the
failed directory and start a new run; never delete rows or overwrite it.

For a harness smoke check only, use fewer than ten batches and keep its output separate:

```bash
MNEME_EVENT_SYNC_MODE=smoke \
MNEME_EVENT_SYNC_ITERATIONS=1 \
tools/evaluation/run_android_formal_event_sync.sh
```

Smoke output is not accepted by the formal analyzer and must not be reported as thesis
evidence.

The runner's repository guard can be checked without an emulator or backend:

```bash
tools/evaluation/run_android_formal_event_sync.sh --self-test
```

This temporary-repository fixture accepts artifacts inside the current run directory and
rejects an unrelated untracked file, an unstaged tracked modification, and a staged
modification.

## Validation and analysis

Run the analyzer against the explicit formal run directory:

```bash
uv run tools/evaluation/analyze_android_formal_event_sync.py \
  docs/evaluation/android-formal/event-sync/raw/formal-<UTC>-<revision>
```

The analyzer requires exactly 50 rows: five ordered stages for each iteration from 1 to
10. It rejects missing or duplicate iterations, failed stages, reused UUIDs, wrong event
counts, incorrect accepted/duplicate results, incorrect final queue states, provenance
hash mismatches, and non-formal manifests. Existing analysis output is never overwritten.

The generated `analysis/` directory contains:

- `validated_raw_order.csv`, which preserves all 50 rows in acquisition order;
- `summary.csv` and `summary.json`, with success count, median, minimum, maximum, and
  range for each stage; and
- `event_sync_latency.png`, showing all ten raw latencies and the median for each stage.

These are descriptive results from one emulator and one isolated backend. No p95,
confidence interval, hypothesis test, deleted outlier, or physical-device generalization
is produced.
