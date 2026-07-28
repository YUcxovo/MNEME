# Explicit-interest correction evaluation

This controlled evaluation checks whether adding, editing, and deleting an
explicit topic changes the inputs and outputs of Mneme's production
recommendation scorer in the expected direction. It complements the behavioral
event evaluation; it does not use clicks or inferred interests as a substitute
for an explicit user correction.

## Protocol

The frozen fixture contains eight synthetic candidates: two each for attention,
quantum, robotics, and databases. All candidates have the same publication
time, so recency is held constant. Four preference states are evaluated:

1. `attention`
2. `attention, quantum` (add quantum)
3. `attention, robotics` (edit quantum to robotics)
4. `attention` (delete robotics)

The runner calls `mneme.ai.recommendation.rank_candidates`, the same production
function used by recommended-digest generation. For every candidate and state
it records rank, score, recommendation reasons, and whether the expected
topic-match reason is present. The transition checks were specified by
direction before the recorded run: adding a topic must raise that topic's mean
score, while replacing or deleting a topic must lower the removed topic's mean
score.

Run from `backend/`:

```bash
uv run python ../tools/evaluation/run_explicit_interest_correction.py
```

## Recorded results

All four directional checks passed.

| Correction | Candidate topic | Mean score before | Mean score after | Mean rank change | Topic-reason rate |
|---|---:|---:|---:|---:|---:|
| Add quantum | quantum | 0.278684 | 0.624838 | 3.5 to 3.5 | 0.0 to 1.0 |
| Edit away from quantum | quantum | 0.624838 | 0.278684 | 3.5 to 5.5 | 1.0 to 0.0 |
| Edit toward robotics | robotics | 0.278684 | 0.624838 | 5.5 to 3.5 | 0.0 to 1.0 |
| Delete robotics | robotics | 0.624838 | 0.278684 | 3.5 to 5.5 | 1.0 to 0.0 |

Adding quantum changed its score and explanation but not its mean rank because
the attention and quantum candidates tied after both topics became active; the
stable paper identifier resolved the tie. The edit and delete operations
changed both score and mean rank. This is useful evidence about mechanism
behavior, including the tie case, rather than a claim about relevance for real
researchers.

The API-level closed-loop test
`test_explicit_preference_update_changes_next_digest_ranking_and_reason`
separately performs a preference `PUT` followed by recommended-digest requests.
It verifies that changing `attention` to `robotics` changes the top paper and
its reason. Repository tests cover normalization, durable replacement, and
rejection of a digest snapshot older than the stored preference update.

## Evidence boundary

The candidates are synthetic and deliberately balanced. The results establish
that explicit corrections propagate through the implemented deterministic
scorer and its explanations under the declared fixture. They do not estimate
real-user preference accuracy, long-term recommendation benefit, diversity, or
user satisfaction.

Artifacts:

- `fixture.json`: frozen inputs and preference states
- `raw/candidate_results.csv`: one row per state and candidate
- `raw/run_manifest.json`: environment and source-file hashes
- `summary.csv`: transition-level outcomes
- `summary.json`: full machine-readable summary
