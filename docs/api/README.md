# API Contract Governance

The frozen OpenAPI document is `openapi-v0.1.yaml`. It remains the v0.1 compatibility baseline between the Android and backend sub-teams. All frozen routes now exist, so FastAPI-generated OpenAPI from the checked-out application is the runtime implementation source of truth.

As of 2026-07-23, FastAPI implements all 13 frozen operations: health, paper list/detail, explicit preferences, seed-paper onboarding, revision-safe summaries, event ingestion, digest list/recommendation, single-paper Q&A, bounded citation graphs, and durable job status. The contract regression compares every operation ID and each documented response's top-level schema reference with `openapi-v0.1.yaml`; focused schema and route tests cover reviewed authentication, parameter, request, payload, and stable-error invariants. This is not a byte-for-byte or complete structural diff of the two OpenAPI documents.

## Ownership

- DRI: Ruiyu Jiang (shared API contract, middleware, non-AI endpoints)
- AI endpoint owner: Yifan Zhang (`summary`, `qa`, `recommended`)
- Android reviewer: Hanyang Wang (DTO compatibility and mock-client usability)
- Data-model reviewer: Yifan reviews AI/RAG fields; Ruiyu approves persistence impact

Any breaking change requires Ruiyu, the endpoint owner, and Hanyang to approve the PR.
The generated document is authoritative for what the running checkout serves. The committed YAML remains the frozen compatibility baseline reviewed by both sub-teams; any intentional difference must update the baseline, Android fixtures, and regression tests in one coordinated change. Breaking changes require a new API version or an explicit coordinated migration.

## Fixed v0.1 Decisions

- Base path: `/v1`
- JSON fields: `snake_case`
- Timestamps: UTC ISO 8601
- Internal resource IDs: UUID strings
- arXiv IDs: separate `arxiv_id` fields; never overload the internal paper ID
- Pagination: cursor-based for lists (`cursor`, `limit`, `next_cursor`)
- Authentication: one pre-provisioned demo token, sent as `Authorization: Bearer <token>`
- No login, registration, password, refresh token, or JWT lifecycle in the MVP
- Async AI work returns `202 Accepted` with a job resource when a result is not ready
- The demo-only seed onboarding coordinator is an explicit exception: it waits for five
  papers and returns one complete `200` response so the Android first-run flow has a single
  loading state. It prefers five arXiv-resolvable citation neighbors, prepares the seed and
  returned papers, and retains same-category selection as the provider-unavailable fallback.
- Errors use the shared `ErrorResponse` schema with a stable machine-readable code
- Paper lists use descending `(published_at, id)` keyset pagination encoded as an opaque cursor
- `PUT /users/me/preferences` is a complete replacement of both explicit preference lists
- Behavioral-event timestamps must be timezone-aware ISO 8601 values and no more than five minutes ahead of the server clock

## Shared Error Codes

| HTTP status | Code | Meaning |
|---|---|---|
| 400 | `invalid_cursor` | A pagination cursor cannot be decoded or validated |
| 400 | `invalid_arxiv_reference` | The seed is not a supported arXiv URL or identifier |
| 401 | `authentication_required` | The Bearer token is missing or malformed |
| 401 | `invalid_token` | The Bearer token does not match the configured demo token hash |
| 404 | `paper_not_found` | The requested internal paper UUID does not exist |
| 404 | `job_not_found` | The requested durable pipeline job does not exist |
| 404 | `conversation_not_found` | The requested Q&A conversation does not belong to the user and paper |
| 404 | `user_not_found` | The configured demo user has not been bootstrapped |
| 404 | `seed_paper_not_found` | arXiv returned no paper for the normalized seed ID |
| 409 | `paper_not_ready` | The paper has no observed revision available for AI work |
| 422 | `validation_error` | Request parameters or JSON do not satisfy the contract |
| 502 | `arxiv_unavailable` | The onboarding coordinator could not read arXiv metadata |
| 502 | `insufficient_related_papers` | arXiv returned fewer than five usable category peers |
| 502 | `seed_initialization_failed` | At least one selected paper failed pipeline processing |
| 502 | `briefing_incomplete` | The completed papers could not form a five-entry briefing |
| 503 | `queue_unavailable` | A required pipeline stage could not be dispatched to ARQ |
| 503 | `service_unavailable` | A required database or upstream dependency is unavailable |
| 504 | `seed_initialization_timeout` | Five-paper preparation exceeded the demo timeout |

Every error includes the request ID. Error details must not contain secrets, full paper text,
provider prompts, or raw database messages.

## Endpoint Ownership

| Endpoint group | Owner |
|---|---|
| health, papers, preferences, events, graph, jobs | Ruiyu |
| seed onboarding | Ruiyu (orchestration), Yifan (AI pipeline), Hanyang (Android consumer) |
| paper summary, Q&A, recommended digest | Yifan |

The endpoint list and schemas are frozen at the end of Milestone 1. Implementation details,
model choices, and ranking parameters may evolve without changing the public contract.
