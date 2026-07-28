# Android live-core evidence retained for the thesis

This directory retains the two successful live-core UI conditions reported in
Chapter 4. The conditions are stored separately because their latency values
must not be pooled.

- `generation-inclusive/` contains the first recorded UI trace and its five
  warm repository repetitions. The UI trace includes live provider generation.
- `artifact-reuse/` contains the later UI trace after the backend had retained
  paper artifacts and could reuse cached provider completions. It also contains
  the two additional live-seed paths.

Both packages contain their own environment record, run manifest, direct CSV
measurements, generated summary, and screenshots. Authentication tokens are not
retained. The two UI traces are single acceptance observations under different
reuse conditions; they are not a repeated cold-versus-warm benchmark.

The additional seed matrix is located at
`artifact-reuse/raw/live_seed_matrix.csv`. Each row requests five papers,
loads a prepared multi-node graph, selects a non-centre node, and opens the
selected paper through the ordinary Android path.
