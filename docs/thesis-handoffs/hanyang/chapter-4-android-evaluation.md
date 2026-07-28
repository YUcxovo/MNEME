# Chapter 4 handoff: Android client evaluation

**Integration owner:** Yifan (`@YifanZhang2026`)

**Intended locations in the thesis template:**

- `Testing Results / Testing Tool`: environment, instrumentation, repetitions,
  and statistics;
- `Testing Results / UI Testing`: controlled state matrix and graph
  interaction checks;
- `Testing Results / Acceptance Testing for Features`: live client event loop
  and end-to-end Android actions;
- `Testing Results / Performance Testing`: start, state-transition, graph, and
  event timing.

## Evaluation questions

The Android evaluation addresses four questions:

1. Does the client enter the expected live, cached, offline, failure, and
   polling states under controlled conditions?
2. Can the graph view render and report node selections at the tested graph
   sizes, including ready, fallback, and empty states?
3. Does a client event remain recoverable after a retryable failure, avoid
   duplicate ingestion, and support a live server readback?
4. What start, foreground/resume, graph, and event-processing latencies are
   observed on the recorded emulator?

These questions concern client reliability and interaction. They do not test
the semantic quality of retrieved papers, generated answers, recommendations,
or graph construction.

## Supervisor-requested product-flow visuals

The retained Android screenshots are stored in:

`docs/thesis-handoffs/hanyang/ui-ux-product-flow/`

The detailed product-level acceptance table is stored in:

`docs/thesis-handoffs/hanyang/feature-acceptance-results.md`

The directory README records the capture environment, data path, and suggested
figure groups. The Chapter 4 front-end development discussion should use the
individual screenshots to present the complete implemented flow:

1. user-entered arXiv seed, processing, and multi-paper briefing;
2. paper detail, structured summary, and citation exploration;
3. node selection and graph-to-paper navigation;
4. open question, processing, cited answer, and source inspection;
5. explicit-interest editing, persistence, and briefing refresh;
6. cached offline content and recovery to the live backend.

Each figure group should be introduced before it appears and interpreted
afterwards. The screenshots are product results from the live integrated
session. The static prototype images in Chapter 3 remain design artifacts and
should not be presented as the final Android implementation.

## Experimental design

### Environment

The recorded experiment used an Android 14/API 34
`sdk_gphone64_x86_64` emulator with four virtual processors and a 192 MiB
application heap. The device fingerprint and complete run metadata are
retained in:

- `docs/evaluation/e4/raw/environment.json`;
- `docs/evaluation/e4/raw/run_manifest.json`.

The live event test used a backend URL visible to the emulator and an
ephemeral authentication token. The token was passed to the instrumentation
process and was not retained.

### Instrumentation and repetitions

Android instrumentation tests wrote one row per measured operation. Warm-up
iterations were executed before collection and discarded:

| Track | Warm-up | Recorded repetitions |
| --- | ---: | ---: |
| Process start and foreground/resume | 3 paired launches | 20 per condition |
| Controlled state transitions | 3 | 30 per non-polling condition |
| Three-stage polling | 1 | 10 |
| New WebView graph | 2 per graph size | 20 per size and action |
| Existing WebView update | 3 per graph size | 30 per size and action |
| Graph ready/fallback/empty states | 3 | 30 per state |
| Controlled event stages | 3 | 30 per stage |
| Live event loop | none retained as data | 5 complete repetitions |

The graph sizes were 1, 12, 25, and 50 nodes. Each graph measurement recorded
DOM-ready latency and the Android node-selection callback latency. DOM
readiness does not imply that the force-directed layout had converged.

The controlled state-transition measurements begin after the deterministic
repository result is available. They measure view-model and state-transition
cost, not network response time. The three-stage polling condition includes
the intended polling interval and therefore has a different time scale.

### Metrics and success conditions

Latency is reported in milliseconds. The p50 value is the sample median and
the p95 value is the nearest-rank 95th percentile. A controlled state sample
was successful when the expected state and disclosure appeared. A graph sample
was successful when the renderer signalled readiness or the Android bridge
reported the selected valid node, depending on the scenario.

For event synchronization, the controlled trace required:

1. a new event to be stored locally;
2. a retryable failure to leave it pending;
3. a later upload to mark it synchronized;
4. a replay of the same identifier to be reported as a duplicate.

The live trace added a client readback after upload. Each repetition used
three new event identifiers. A successful repetition required the live server
to accept the three new events, recognize the same three identifiers on
replay, and return a live briefing response.

### Retained data and analysis

The direct measurements are stored in
`docs/evaluation/e4/raw/`. The analysis script validates the expected sample
counts and success fields before producing `summary.csv`, `summary.json`, and
the figures. The connected-device XML retains the results of five application
flow tests and six graph tests. The complete reproduction commands are
documented in `docs/evaluation/e4/README.md`.

## Results

### Overall correctness

All 810 controlled measurement samples met their stated success conditions.
All 25 live-backend stages also succeeded. Eleven existing application-flow
and graph tests passed. These counts establish consistency for the tested
conditions; they do not establish correctness for all devices or server
states.

### Application start and controlled states

| Scenario | n | Success | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Cold process start | 20 | 20/20 | 2773.000 | 4444.000 |
| Task foreground/resume | 20 | 20/20 | 133.500 | 445.000 |
| Live seed state transition | 30 | 30/30 | 0.124 | 0.293 |
| Cached warm state | 30 | 30/30 | 0.227 | 0.376 |
| Cached offline disclosure | 30 | 30/30 | 0.227 | 0.439 |
| Cached server-failure disclosure | 30 | 30/30 | 0.231 | 0.362 |
| Invalid-cache error | 30 | 30/30 | 0.203 | 0.635 |
| Three-stage job polling | 10 | 10/10 | 3008.418 | 3064.345 |

Android classified nine foreground/resume measurements as `HOT` and returned
`UNKNOWN (0)` for eleven. The result must therefore be described as the
measured task foreground/resume operation, not as 20 confirmed hot starts.
The state-transition rows are controlled client costs after the result is
available and must not be presented as end-to-end network latency.

### Citation-graph rendering

#### DOM-ready latency

| Nodes | New WebView p50 / p95 (ms) | Existing WebView p50 / p95 (ms) |
| ---: | ---: | ---: |
| 1 | 139.749 / 298.019 | 83.001 / 150.840 |
| 12 | 454.149 / 913.746 | 95.590 / 331.895 |
| 25 | 315.039 / 734.190 | 97.767 / 361.523 |
| 50 | 306.793 / 928.176 | 111.814 / 513.785 |

#### Node-selection callback latency

| Nodes | New WebView p50 / p95 (ms) | Existing WebView p50 / p95 (ms) |
| ---: | ---: | ---: |
| 1 | 32.764 / 46.022 | 32.279 / 103.680 |
| 12 | 35.971 / 392.792 | 32.968 / 208.816 |
| 25 | 48.675 / 568.963 | 32.759 / 128.642 |
| 50 | 49.098 / 353.710 | 37.860 / 163.644 |

All graph timing samples succeeded. The ready, fallback, and empty-state
conditions also succeeded in 30 out of 30 repetitions each, with median
latencies of 97.114, 103.375, and 66.281 ms respectively.

The medians do not increase monotonically with node count, and several p95
values are much larger than their medians. The retained data therefore do not
support a fitted scaling law. Within the tested range, WebView creation and
emulator scheduling appear to contribute more variability than node count.
Updating an existing WebView produced lower median DOM-ready latency at every
tested size, which supports retaining the renderer between graph updates in
this measured configuration.

### Event synchronization

#### Controlled event stages

| Stage | n | Success | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Local queue write | 30 | 30/30 | 10.287 | 32.261 |
| Retryable failure handling | 30 | 30/30 | 15.613 | 80.332 |
| Retry upload success | 30 | 30/30 | 54.999 | 91.794 |
| Duplicate replay | 30 | 30/30 | 18.950 | 50.222 |

#### Live-backend stages

| Stage | n | Success | p50 (ms) | p95 (ms) |
| --- | ---: | ---: | ---: | ---: |
| Local queue write | 5 | 5/5 | 13.850 | 19.061 |
| Controlled failure before live retry | 5 | 5/5 | 8.028 | 8.616 |
| Live retry upload | 5 | 5/5 | 33.049 | 188.478 |
| Duplicate replay | 5 | 5/5 | 24.210 | 125.869 |
| Client readback | 5 | 5/5 | 26.776 | 135.906 |

In each live repetition, the server accepted three new event identifiers and
reported the same three identifiers as duplicates on replay. The subsequent
briefing response had a live-backend origin and preference-model version 1.
The returned digest contained zero papers in all five repetitions because the
evaluation database had no candidates in the active digest window. The trace
therefore demonstrates reachability, recoverable upload, and idempotent
ingestion. It does not demonstrate a successful recommendation or preference
adaptation.

## Threats to validity and limitations

- Measurements were taken on one emulator configuration. Physical devices and
  other Android versions may produce different start and WebView timings.
- The controlled repository isolates Android state transitions. It improves
  repeatability but excludes network and server latency.
- Five live repetitions are sufficient to retain a concrete integration trace,
  but they are too few for a broad performance distribution.
- DOM readiness marks the renderer callback and does not measure convergence
  of the force-directed layout or the time required to interpret the graph.
- Graphs contained at most 50 nodes. The results should not be extrapolated to
  substantially larger graphs.
- The event test establishes transport and idempotency behaviour. Its
  zero-entry digest cannot support conclusions about recommendation quality.
- The evaluation contains no user study of the revised graph interface.

## Figures available for Chapter 4

- `docs/evaluation/e4/figures/mobile_reliability.pdf`
- `docs/evaluation/e4/figures/graph_latency.pdf`
- `docs/evaluation/e4/figures/android_client_loop.pdf`

PDF should be used in LaTeX for vector-quality output. The PNG versions are
available for repository previews.

## Sample thesis writing

The following text may be adapted into Chapter 4. The subsection titles should
be aligned with the surrounding chapter rather than copied mechanically.

### Sample for Testing Tool

The Android evaluation was executed on an Android 14/API 34 emulator with four
virtual processors and a 192 MiB application heap. Instrumentation tests wrote
one record for each measured operation, while a separate analysis program
validated the sample counts and success conditions before computing the sample
median and nearest-rank 95th percentile. Warm-up iterations were discarded
before measurement. The experiment retained 20 observations for each start
condition, 30 observations for most controlled client states, 20 or 30
observations for each graph configuration, and five repetitions of the live
event loop. Controlled and live results were analysed separately because
deterministic repositories exclude network and server latency.

### Sample for UI Testing

The controlled state matrix covered live content, cached content, offline
recovery, server failure with retained content, invalid cache data, and a
three-stage asynchronous paper job. All 160 measured state samples reached
their expected outcome. The five non-polling transitions had median
client-side costs between 0.124 and 0.231 ms. These values describe state
processing after a deterministic result is available. The three-stage polling
condition had a median duration of 3008.418 ms because it includes the intended
polling interval.

The graph evaluation used graphs containing 1, 12, 25, and 50 nodes. All 400
rendering and selection measurements succeeded. For a newly created WebView,
median DOM-ready latency ranged from 139.749 to 454.149 ms. Updating an
existing WebView reduced this range to 83.001--111.814 ms. Median
node-selection callback latency remained between 32.279 and 49.098 ms across
the measured configurations. Ready, fallback, and empty graph states each
reached the expected interface state in all 30 repetitions. The measurements
mark DOM readiness and the Android callback; they do not measure convergence
of the force-directed layout.

### Sample for Acceptance Testing for Features

Five live repetitions evaluated the client event loop. Each repetition stored
three new events locally, preserved them after a controlled retryable failure,
uploaded them to the live server, replayed the same identifiers, and requested
a new briefing. The server accepted all three new identifiers and recognized
all three replays as duplicates in every repetition. The readback returned a
live-backend response with preference-model version 1. Its digest contained no
papers because the evaluation database had no candidates in the active digest
window. This result confirms client-loop reachability, retry recovery, and
idempotent ingestion for the recorded cases. It provides no evidence about
recommendation quality or behavioural adaptation.

### Sample for Performance Testing

Cold process start had a median of 2773 ms and a p95 of 4444 ms. The measured
task foreground/resume operation had a median of 133.5 ms and a p95 of 445 ms.
Only nine of the latter operations were classified as hot starts by Android;
the remaining eleven had an unknown launch classification, so the measurement
is reported as foreground/resume rather than a pure hot-start benchmark.

The graph results showed substantial upper-tail variability and no monotonic
increase in median latency with node count. This pattern does not justify a
scaling claim. It indicates that WebView initialization and emulator scheduling
were important sources of variation within the tested range. Reusing the
existing WebView nevertheless produced a lower median DOM-ready latency at all
four graph sizes. In the live event trace, upload and client readback had
medians of 33.049 and 26.776 ms respectively. These live values are retained
as a small integration trace and are not treated as a general server
performance benchmark.

## Integration checks

Before incorporating this material, the Chapter 4 owner should:

1. keep controlled client timings separate from live-network timings;
2. describe the foreground/resume result using its measured launch
   classifications;
3. state that graph timing ends at DOM readiness;
4. retain the zero-entry digest result and its interpretation;
5. avoid conclusions about AI, recommendation, graph-algorithm, notification,
   or worker quality;
6. cite the retained artifact or table for every numerical claim.
