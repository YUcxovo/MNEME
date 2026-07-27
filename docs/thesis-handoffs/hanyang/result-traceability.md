# Android E4 result traceability

This table is the claim boundary for the Chapter 4 sample writing. A claim may
be shortened during integration, but its interpretation must not be broadened.

| Claim | Retained source | Permitted interpretation | Excluded interpretation |
| --- | --- | --- | --- |
| 20 cold starts: p50 2773 ms, p95 4444 ms | `raw/app_start_measurements.csv`; `summary.json` | Start timing on the recorded emulator | General Android-device start performance |
| 20 foreground/resume operations: p50 133.5 ms, p95 445 ms | `raw/app_start_measurements.csv`; `summary.json` | Timing of the measured task foreground/resume operation | 20 independently confirmed hot starts |
| Controlled live, cached, offline, server-failure, and invalid-cache states all succeeded | `raw/state_measurements.csv`; `summary.json` | Expected Android state transition under deterministic input | Network or server latency |
| Three-stage polling: 10/10, p50 3008.418 ms | `raw/state_measurements.csv`; `summary.json` | Expected polling sequence including its interval | Backend job completion performance |
| 1, 12, 25, and 50-node graph timing samples all succeeded | `raw/graph_measurements.csv`; `summary.json` | DOM-ready and Android selection-callback timing | Graph algorithm quality or force-layout convergence |
| Ready, fallback, and empty states each succeeded 30/30 | `raw/graph_state_measurements.csv`; `summary.json` | Android disclosure-state correctness | User comprehension or usability |
| Five application-flow tests and six graph tests passed | `raw/connected_android_test_results.xml` | Correctness of the retained tested paths | Complete correctness of the Android application |
| Controlled queue, retry, success, and duplicate stages each succeeded 30/30 | `raw/event_sync_measurements.csv`; `summary.json` | Deterministic client event-state behaviour | Live server reliability |
| All 25 live stages succeeded | `raw/live_event_closed_loop.csv`; `summary.json` | Five recorded client-to-server closed-loop traces | Broad service availability |
| Three new identifiers were accepted and three replays were duplicates per live repetition | `raw/live_event_closed_loop.csv`; `summary.json` | Idempotent ingestion for the recorded identifiers | General duplicate detection under every workload |
| Live readback returned origin `LIVE_BACKEND` and preference-model version 1 | `raw/live_event_closed_loop.csv`; `summary.json` | The client reached and decoded the live briefing endpoint | Preference-model quality |
| Live digest entry count was zero in all five repetitions | `raw/live_event_closed_loop.csv`; `summary.json` | No candidate occurred in the active evaluation window | Successful recommendation or adaptation |
| 810 controlled samples and 25 live stages met their conditions | Raw CSV files; `summary.json`; `docs/evaluation/e4/README.md` | Aggregate count for this recorded experiment | Statistical proof over unseen devices or workloads |

## Sample-count reconciliation

The 810 controlled samples consist of:

- 40 start and foreground/resume observations;
- 160 controlled state and polling observations;
- 400 graph rendering and selection observations;
- 90 graph ready, fallback, and empty-state observations;
- 120 controlled event-stage observations.

The 25 live stages consist of five stages in each of five live repetitions.
The eleven connected-device correctness tests are reported separately and are
not included in either measurement total.
