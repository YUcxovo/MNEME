# Android E4 evaluation

This directory contains the reproducible Android client evaluation used for the
mobile part of E4. It separates controlled state-transition measurements from
the live-backend trace so that a fast local fixture cannot be mistaken for
network performance.

## Scope

The evaluation covers:

- cold process start and warm task resume;
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
and warm launch pairs. Controlled state, graph, and event tests have their own
discarded warm-up iterations. The live event loop runs five independent
repetitions against the configured backend.

## Artifacts and interpretation

`raw/` retains the direct CSV output, device environment, and run manifest.
`summary.csv` and `summary.json` contain sample counts, successful outcomes,
sample medians, and nearest-rank 95th percentiles. `figures/` contains the
result plots and an architecture figure.

Every controlled result is labelled as controlled. The live readback records
the number of digest entries and preference-model version returned by the
backend. A zero-entry digest is a valid measured outcome and must not be
rewritten as a successful recommendation result.
