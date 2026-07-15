# AI Schema Review and Evaluation Seed (Milestone 1)

Owner: Yifan Zhang. Two deliverables from the Day 2 contract/schema workshop:
the AI-side review of the frozen artifact schema (ER v0.1), and the frozen
evaluation fixture format with the first five QA seed cases.

## AI/RAG schema review (ER v0.1)

Reviewed against the needs of summarization (M2), chunking/embedding (M2),
retrieval + grounded QA (M3), and evaluation (M4). **Approved as frozen**,
with the notes below.

### `paper_chunks` — approved

- Chunks bind to `paper_version_id`, not just `paper_id`: retrieval results
  and citations stay reproducible when arXiv publishes a revision. Correct.
- `section_title`, `chunk_index`, `page_start`/`page_end` carry everything the
  section-aware chunker (M2) and citation rendering (M3) need.
- `embedding vector(1536)` with a paired `embedding_model` column, and a check
  constraint that either both or neither are set — prevents orphan vectors
  after a model swap. 1536 dims fits the default embedding tier of both
  candidate providers.
- `content_hash` enables idempotent re-chunking; the unique
  `(paper_version_id, chunk_index)` key makes writes retry-safe.
- Note for M2: `token_count` should be populated by the chunker so retrieval
  can budget context windows without re-tokenizing.

### `paper_summaries` — approved

- The generation-identity unique key `(paper_version_id, input_hash, provider,
  model_snapshot, prompt_version)` matches the cache-key design in
  `ai-services.md`: one row per distinct generation, reruns are idempotent.
- Telemetry columns (`estimated_cost`, `input_tokens`, `output_tokens`,
  `latency_ms`) line up 1:1 with `CompletionResult`, so the summarization
  worker can persist results without translation.
- `content` as JSONB keeps the structured summary (tldr, key claims,
  methodology, limitations) flexible while the public contract stays frozen
  in the API schema.

### `qa_messages` — approved

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
format change bumps `fixture_version` (never edit cases in place — add a new
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
