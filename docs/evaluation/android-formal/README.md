# Formal Android resource experiment

This directory defines the small formal Android experiment used to evaluate
startup/recovery latency and bounded citation-graph rendering under controlled
CPU and RAM settings. It contains the protocol only. Formal observations are
created under a new `raw/<run-id>/` directory by the runner; this README does
not report pilot or formal results.

## Scope

The experiment varies two emulator resources:

| Configuration ID | Virtual CPU cores | Emulator RAM |
|---|---:|---:|
| `cpu2_ram2gb` | 2 | 2 GiB |
| `cpu2_ram6gb` | 2 | 6 GiB |
| `cpu4_ram2gb` | 4 | 2 GiB |
| `cpu4_ram6gb` | 4 | 6 GiB |

The protocol has two complementary blocks:

1. `cpu2_ram2gb`, `cpu2_ram6gb`, `cpu4_ram6gb`, `cpu4_ram2gb`
2. `cpu4_ram2gb`, `cpu4_ram6gb`, `cpu2_ram6gb`, `cpu2_ram2gb`

The second block is the exact reverse of the first. Each resource cell
therefore has two separately cold-booted sessions, for eight sessions in
total. This is an order-reversed small-sample design, not a fully
counterbalanced factorial experiment. The session is the analysis unit; the
protocol does not claim statistical independence or population sampling.

One session is one wiped-data, cold-boot emulator process. The runner rejects
an already connected device or emulator, starts one dedicated AVD with the
requested resources, records its boot ID, and stops it before the next
session. The host CPU affinity is fixed across all sessions.

## Measurements within one session

### Startup and foreground recovery

The standard AndroidX Macrobenchmark output is the raw source. Each benchmark
method performs six recorded iterations. Raw iteration 1 is a protocol warm-up
and remains available in the native `benchmarkData.json`; the analyzer excludes
it from the formal CSV. Raw iterations 2--6 become five retained observations.

- Cached cold start uses `timeToFullDisplayMs`. The application calls
  `reportFullyDrawn` only after the cached five-paper content is displayed.
- Foreground recovery uses `timeToInitialDisplayMs` on the same Activity and
  process. The benchmark test is responsible for asserting the expected
  process ID and UI marker before the method succeeds. A previously consumed
  `reportFullyDrawn` event is not reused as a foreground-recovery metric.

The analyzer rejects a substituted metric, a non-positive duration, a failed
benchmark task, or any session that does not contain exactly five retained
observations for each scenario.

### Citation-graph rendering

The instrumentation method is:

```text
com.mneme.app.ui.graph.E4GraphMeasurementTest#recordBoundedRendererLatency
```

Each session measures 1, 12, 25, and 50 nodes. Block 1 uses ascending node
order; Block 2 uses descending node order. For every node count, one complete
new/reused WebView pair is a warm-up and five complete pairs are retained. A
retained pair contains:

1. rendering in a newly created WebView; and
2. rendering the same graph again in that WebView.

The ready condition is a renderer-emitted visual-state marker with the expected
DOM node/edge counts and at least one renderer tick. The resulting formal CSV
contains exactly 40 rows per session:

```text
4 node counts x 5 retained pairs x 2 WebView phases
```

The validator checks the declared node order, DOM counts, success state,
render identifiers, and paired WebView identifiers. It does not substitute a
fixed sleep for renderer readiness.

## Prerequisites

Use a dedicated API 34 AVD. The default name is
`Mneme_Factorial_API_34_Pixel6`. JDK 17 and the Android SDK must be installed.
The runner additionally requires `jq`, `timeout`, `sha256sum`, `uuidgen`,
`flock`, `taskset`, `realpath`, Python 3, `uv`, and Git. Run it from the
repository root.

No live backend, API key, demo token, provider, or network corpus is used. The
startup benchmark seeds a deterministic five-paper state into the production
Room schema before timing, and the graph benchmark constructs its bounded
fixture locally. The runner passes an unreachable loopback endpoint and an
explicitly blank demo token while building the debug graph APK. The benchmark
build type uses its cache-only sentinel. Manifests record
`backend_used: false` and the two controlled data sources. The evidence
directory stores APK paths and SHA-256 hashes, not APK copies.
The runner rejects inherited Java/Gradle option variables that JVM launchers
would echo into retained logs, and removes live MNEME endpoint/token variables
before invoking Gradle.

Defaults for the standard benchmark module are:

```text
Gradle task:
  :benchmark:connectedBenchmarkAndroidTest

Benchmark class:
  com.mneme.app.benchmark.MnemeStartupBenchmark

Additional-output root:
  android/benchmark/build/outputs/
    connected_android_test_additional_output/benchmark/connected

Target APK:
  android/app/build/outputs/apk/benchmark/app-benchmark.apk

Benchmark APK:
  android/benchmark/build/outputs/apk/benchmark/benchmark-benchmark.apk
```

The runner locks these tested tasks and artifact paths. If a future Android
Gradle Plugin version changes them, update and revalidate the protocol tooling
before acquisition instead of overriding a path at run time.

The default host affinity is CPUs 4--11. Override it only before the run:

```bash
export MNEME_FORMAL_HOST_CPUSET='4-11'
```

## Formal acquisition

The runner deliberately refuses a dirty worktree, an existing run ID, an
already connected Android device, or a concurrent formal run. It builds once,
freezes the four APK hashes, and verifies those hashes around every session.
Before marking the run complete, it also verifies that the Git revision,
branch, tracked files, index, runner, and analyzer are unchanged. At that final
check, the only permitted new Git-visible files are those below the exact
current run directory.

```bash
tools/evaluation/run_android_formal_resource_matrix.sh
```

For an explicit evidence identifier:

```bash
MNEME_FORMAL_RUN_ID='resource-formal-YYYYMMDD' \
  tools/evaluation/run_android_formal_resource_matrix.sh
```

Do not run another emulator, Gradle build, or performance experiment in
parallel. Do not manually delete or edit a session directory during
acquisition.

Every timed measurement and analysis command has a `.txt` stdout/stderr record
and a row in `commands.tsv`. Dedicated top-level and session files retain the
host and guest environment observations. Each session also retains its source
revision, script and APK hashes, emulator PID and serial, unique boot ID,
requested and observed resources, build fingerprint, WebView package, host
load/memory snapshots, raw Macrobenchmark artifacts, and graph artifacts.

If a benchmark or session step fails, the runner retains available output,
pulls any available device artifacts, and writes `failed.json`. It does not
remove failed samples, restart the session, or retry automatically. Diagnose
the retained failure and begin a new run ID if the protocol needs to be
repeated.

## Validation and analysis

The runner validates every session before proceeding. A retained run can also
be analyzed independently:

```bash
tools/evaluation/analyze_android_formal_resource_matrix.py analyze \
  --run-root docs/evaluation/android-formal/raw/resource-formal-YYYYMMDD
```

The analyzer treats each separately cold-booted session as the analysis unit:

1. five retained observations become one median within each session;
2. both session medians for each resource cell are preserved;
3. their median, minimum, maximum, and explicit max-minus-min range are
   reported;
4. CPU and RAM simple effects and their descriptive interaction are calculated
   separately for each block; and
5. graph-latency curves retain the two session medians at each node count.

Outputs include CSV tables, a machine-readable JSON summary, and graph/resource
figures. In the figures, `x` and `+` identify Block 1 and Block 2 session
medians, respectively. With only two sessions per cell, the analyzer does not
calculate p95, confidence intervals, significance tests, or population-level
hardware effects. The results support descriptive comparison on the recorded
host and emulator configuration.
