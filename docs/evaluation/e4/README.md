# Android E4 evaluation

This directory contains the reproducible Android client evaluation used for the
mobile part of E4. It separates controlled state-transition measurements from
the live-backend trace so that a fast local fixture cannot be mistaken for
network performance.

## Scope

The evaluation covers:

- cold process start and task foreground/resume;
- live, cached, offline, server-failure, and invalid-cache UI states;
- asynchronous paper-job polling;
- graph rendering at 1, 12, 25, and 50 nodes;
- graph ready, fallback, and empty-state disclosure;
- node-selection bridging, the existing Open Paper flow, and selection restore;
- client event queueing, retry, duplicate handling, live upload, and client
  readback.

It does not evaluate retrieval quality, generated-answer quality,
recommendation quality, graph ranking or clustering quality, or notification
and worker internals. The graph timing marks DOM readiness and the Android
selection callback. It does not claim that the D3 force simulation has
converged.

## Run

Start a backend that is visible to the emulator and provide a real demo token:

```bash
export MNEME_E4_LIVE_BASE_URL=http://10.0.2.2:8000/v1/
export MNEME_E4_LIVE_TOKEN='<ephemeral raw token>'
tools/evaluation/run_android_e4_evaluation.sh
uv run tools/evaluation/analyze_android_e4.py
```

The runner requires one Android device or emulator, JDK 17, the Android SDK,
and `jq`. It fails before measurement if the live URL or token is absent. The
token is passed to the instrumentation process and is not written to an
artifact.

The runner performs three warm-up launch pairs followed by 20 measured cold
process starts and 20 measured task foreground/resume operations. Controlled
state, graph, and event tests have their own discarded warm-up iterations. The
live event loop runs five repetitions against the configured backend.

## Artifacts and interpretation

`raw/` retains the direct CSV output, device environment, run manifest, and the
connected Android test result XML.
`summary.csv` and `summary.json` contain sample counts, successful outcomes,
sample medians, and nearest-rank 95th percentiles. `figures/` contains the
result plots and an architecture figure.

Every controlled result is labelled as controlled. The live readback records
the number of digest entries and preference-model version returned by the
backend. A zero-entry digest is a valid measured outcome and must not be
rewritten as a successful recommendation result.

## Recorded run

The recorded run used the Android 14/API 34 `sdk_gphone64_x86_64` emulator with
four virtual processors and a 192 MiB application heap. All 810 controlled
samples and all 25 live-backend stages met their stated success conditions.
Eleven existing graph and app-flow tests also passed, including the selected
paper's Open Paper action and selection restoration after back navigation.
The retained XML comes from `./gradlew connectedDebugAndroidTest` on the same
source snapshot and emulator. It identifies the five `MnemeAppFlowTest` cases
and six `GraphScreenTest` cases used for this count.

The cold-process start had a 2,773 ms median and a 4,444 ms p95. The task
foreground/resume operation had a 133.5 ms median and a 445 ms p95. All 20
operations returned a non-empty `WaitTime` record for `MainActivity`; the
startup runner does not inspect rendered UI content. Android classified 9 as
`HOT` and returned `UNKNOWN (0)` for 11; the distribution therefore
characterizes the measured foreground/resume operation and is not presented as
20 independently confirmed hot starts. The retained latency is the
`wait_time_ms` field because `total_time_ms` is blank for the unknown launch
class. Across the four graph sizes,
median DOM-ready latency ranged from 139.749 to 454.149 ms for a new WebView
and from 83.001 to 111.814 ms for an existing WebView. Median node-selection
callback latency ranged from 32.28 to 49.098 ms.

Each of the five live repetitions uploaded three new events, recognized the
same three identifiers on replay, and returned a live briefing model to the
client. The live upload median was 33.049 ms, and client readback was 26.776
ms. The returned digest contained zero papers in every repetition because the
local evaluation database had no candidates in the active digest window. The
run therefore demonstrates client-loop reachability and idempotent ingestion,
not recommendation quality or adaptation.
