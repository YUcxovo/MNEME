# Android CPU x RAM factorial evaluation

This evaluation isolates emulated CPU and RAM while keeping Android 14/API 34,
the Pixel 6 device profile, the Google APIs x86_64 system image, screen size,
density, application heap, build, host, and measurement code fixed. It uses a
2x2 factorial design with four counterbalanced blocks. Every session starts
from a wiped-data cold boot.

The independent unit is one emulator session. Each session contains 810
repeated controlled samples, but those samples are not treated as 810
independent devices. The analysis uses per-session medians and summarizes the
four independent values in each factorial cell. Exact finite bootstrap
intervals enumerate every resample of the four session summaries.

Across all sessions, 12960/12960 controlled samples
met their predefined success conditions. Each configuration also passed eleven
functional graph and app-flow tests during its first block.

| CPU cores | RAM (GiB) | Independent sessions | Successful samples | Cold start median (ms) | 50-node new WebView (ms) | 50-node reused WebView (ms) | Construction/reuse ratio |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 2 | 4 | 3240/3240 | 2252.8 | 168.6 | 92.5 | 1.8x |
| 2 | 6 | 4 | 3240/3240 | 1842.8 | 167.0 | 91.0 | 1.8x |
| 4 | 2 | 4 | 3240/3240 | 1328.2 | 5099.5 | 83.0 | 61.1x |
| 4 | 6 | 4 | 3240/3240 | 1198.8 | 5099.4 | 83.2 | 61.3x |

Factor effects below are block-level percentage changes. Negative values mean
lower latency at the higher factor level. With four blocks, they are
descriptive estimates and are not presented as population-level significance
tests.

| Metric | Factor | Median block change | Block IQR |
|---|---|---:|---:|
| Cold process start | CPU | -38.6% | [-42.9%, -36.7%] |
| Cold process start | RAM | -13.7% | [-14.9%, -12.9%] |
| Task foreground / resume | CPU | -14.1% | [-21.2%, -8.5%] |
| Task foreground / resume | RAM | -9.8% | [-13.7%, -6.6%] |
| 50-node new WebView | CPU | +2882.1% | [+2804.1%, +2963.8%] |
| 50-node new WebView | RAM | -0.1% | [-0.1%, +2.8%] |
| 50-node existing WebView | CPU | -9.7% | [-11.0%, -7.1%] |
| 50-node existing WebView | RAM | -0.4% | [-2.9%, +2.3%] |
| 50-node selection callback | CPU | -4.6% | [-6.6%, -3.9%] |
| 50-node selection callback | RAM | -0.9% | [-2.1%, +0.2%] |

The experiment excludes backend, retrieval, model, and recommendation quality.
New-WebView readiness records the expected DOM nodes and renderer marker; it
does not claim convergence of the force simulation. Emulator results on one
host establish controlled implementation behavior and repeatability within
the tested resource range. They do not represent the distribution of physical
Android devices.

## Reproduction

```bash
tools/evaluation/run_android_factorial_evaluation.sh
uv run --script tools/evaluation/analyze_android_factorial.py
```

Raw CSV files, test outputs, emulator logs, environment records, run order, and
session manifests are retained under `raw/`.
