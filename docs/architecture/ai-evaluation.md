# AI Schema Review and Evaluation Seed (Milestone 1)

Owner: Yifan Zhang. Two deliverables from the Day 2 contract/schema workshop:
the AI-side review of the frozen artifact schema (ER v0.1), and the frozen
evaluation fixture format with the first five QA seed cases.

## AI/RAG schema review (ER v0.1)

Reviewed against the needs of summarization (M2), chunking/embedding (M2),
retrieval + grounded QA (M3), and evaluation (M4). **Approved as frozen**,
with the notes below.

### `paper_chunks` -- approved

- Chunks bind to `paper_version_id`, not just `paper_id`: retrieval results
  and citations stay reproducible when arXiv publishes a revision. Correct.
- `section_title`, `chunk_index`, `page_start`/`page_end` carry everything the
  section-aware chunker (M2) and citation rendering (M3) need.
- `embedding vector(1536)` with a paired `embedding_model` column, and a check
  constraint that either both or neither are set -- prevents orphan vectors
  after a model swap. 1536 dims fits the default embedding tier of both
  candidate providers.
- `content_hash` enables idempotent re-chunking; the unique
  `(paper_version_id, chunk_index)` key makes writes retry-safe.
- Note for M2: `token_count` should be populated by the chunker so retrieval
  can budget context windows without re-tokenizing.

### `paper_summaries` -- approved

- The generation-identity unique key `(paper_version_id, input_hash, provider,
  model_snapshot, prompt_version)` matches the cache-key design in
  `ai-services.md`: one row per distinct generation, reruns are idempotent.
- Telemetry columns (`estimated_cost`, `input_tokens`, `output_tokens`,
  `latency_ms`) line up 1:1 with `CompletionResult`, so the summarization
  worker can persist results without translation.
- `content` as JSONB keeps the structured summary (tldr, key claims,
  methodology, limitations) flexible while the public contract stays frozen
  in the API schema.

### `qa_messages` -- approved

- Same provenance and telemetry columns as summaries (`provider`,
  `model_snapshot`, `prompt_version`, `input_hash`, cost/tokens/latency),
  nullable for user turns. `citations` JSONB matches the frozen `Citation`
  contract shape.
- Note for M3: `source_match_status` on the assistant turn is the anchor for
  the source-match rate metric; the eval harness will read it directly.

## Evaluation fixture format (frozen)

Fixture files are JSON with a versioned envelope, validated by
`mneme.ai.evaluation.fixtures.QAFixtureFile`:

```json
{
  "fixture_version": "qa-seed-v1",
  "fixtures": [
    {
      "fixture_id": "qa-001-transformer-attention",
      "arxiv_id": "1706.03762",
      "section_hint": "Model Architecture",
      "question": "...",
      "reference_answer": "...",
      "expected_keywords": ["attention", "self-attention", "multi-head"],
      "must_cite": true
    }
  ]
}
```

| Field | Purpose |
|---|---|
| `fixture_id` | Stable unique ID; metrics are tracked per fixture across runs |
| `arxiv_id` | The paper the question targets; must be ingested before a live run |
| `section_hint` | Where the answer lives; used to judge retrieval placement |
| `question` | The user question sent to the pipeline |
| `reference_answer` | Manually written gold answer for human comparison |
| `expected_keywords` | Drives the M1 keyword-coverage placeholder metric |
| `must_cite` | Whether a grounded answer must carry at least one citation |

Rules: `fixture_id` values are unique per file, files are ASCII-only, and any
format change bumps `fixture_version` (never edit cases in place -- add a new
version so metric history stays comparable).

## Seed cases (qa-seed-v1)

Five manually checked cases in `backend/tests/fixtures/eval/qa_seed_v1.json`,
chosen to be answerable from a single well-known cs.AI/cs.LG paper each, so
they exercise single-paper QA (the M3 scope) without cross-paper synthesis:

1. `qa-001` Transformer attention (1706.03762)
2. `qa-002` LoRA trainable parameters (2106.09685)
3. `qa-003` DDPM training objective (2006.11239)
4. `qa-004` RAG components (2005.11401)
5. `qa-005` DPO vs reward models (2305.18290)

M2 expands the set alongside the summarization prompt; M4 grows it to 10-20
pairs and adds recall@k, source-match rate, and helpfulness on top of the
keyword-coverage placeholder.

## Expanded set (qa-seed-v2, Milestone 4)

`backend/tests/fixtures/eval/qa_seed_v2.json` grows the set to 15 cases. The
five v1 cases keep their `fixture_id` values so per-fixture metric history
stays comparable across versions. Ten new cases split into:

- Seven answerable cases covering two additional papers (BERT 1810.04805,
  ViT 2010.11929) plus second questions against the v1 papers, so recall@k
  is graded against more than one section per paper.
- Three out-of-scope cases marked `expect_refusal: true` (with
  `must_cite: false` and no keywords): the correct behavior is the stable
  refusal answer. These grade calibrated refusal instead of answer quality.

The format change adding `expect_refusal` bumped the fixture version per the
rules above; v1 files remain valid because the field defaults to `false`.

## RAG-graded metrics (Milestone 4)

`RagEvaluationHarness` drives the full retrieval + grounded-answer pipeline
(not just completion text) and reports, per run:

| Metric | Definition |
|---|---|
| `recall_at_k` | Answerable fixtures with a `section_hint` whose retrieved chunks include a section matching the hint (containment either direction, casefolded) |
| `source_match_rate` | Answered cases whose `source_match_status` is fully MATCHED; PARTIAL is reported separately as `partial_match_rate`, never folded in |
| `citation_rate` | Answered cases carrying at least one verified citation |
| `refusal_accuracy` | `expect_refusal` fixtures that were actually refused |
| `false_refusal_rate` | Answerable fixtures wrongly refused |
| `mean_keyword_coverage` | Keyword coverage over answered answerable cases (helpfulness placeholder; real helpfulness needs human judgment) |
| tokens / cost / latency | Summed from `CompletionResult` telemetry; refusals that never reach the provider contribute zero |

Rates are `null` when no fixture in the set applies to them. Keyword coverage
remains a lexical placeholder: it measures term presence, not semantic
correctness, and is never reported as helpfulness without human review.
