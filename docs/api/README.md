# API Contract Governance

The frozen OpenAPI document is `openapi-v0.1.yaml`. It is the contract between the Android
and backend sub-teams until every v0.1 route exists and FastAPI can become the complete
generated source of truth.

As of 2026-07-15, FastAPI implements and contract-tests `health`, `papers`, and
`users/me/preferences`. Later-milestone summary, event, digest, Q&A, graph, and job routes
remain represented only by the frozen contract.

## Ownership

- DRI: Ruiyu Jiang (shared API contract, middleware, non-AI endpoints)
- AI endpoint owner: Yifan Zhang (`summary`, `qa`, `recommended`)
- Android reviewer: Hanyang Wang (DTO compatibility and mock-client usability)
- Data-model reviewer: Yifan reviews AI/RAG fields; Ruiyu approves persistence impact

Any breaking change requires Ruiyu, the endpoint owner, and Hanyang to approve the PR.
The committed contract remains authoritative while later-milestone routes are absent or only
skeletons. Backend contract tests inspect FastAPI's generated OpenAPI in CI and check every
implemented route and shared schema against this contract. The generated document becomes
authoritative only after all frozen routes are represented in the application. Breaking
changes require a new API version or an explicit coordinated migration.

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
- Errors use the shared `ErrorResponse` schema with a stable machine-readable code
- Paper lists use descending `(published_at, id)` keyset pagination encoded as an opaque cursor
- `PUT /users/me/preferences` is a complete replacement of both explicit preference lists

## Shared Error Codes

| HTTP status | Code | Meaning |
|---|---|---|
| 400 | `invalid_cursor` | A pagination cursor cannot be decoded or validated |
| 401 | `authentication_required` | The Bearer token is missing or malformed |
| 401 | `invalid_token` | The Bearer token does not match the configured demo token hash |
| 404 | `paper_not_found` | The requested internal paper UUID does not exist |
| 404 | `user_not_found` | The configured demo user has not been bootstrapped |
| 422 | `validation_error` | Request parameters or JSON do not satisfy the contract |
| 503 | `service_unavailable` | A required database or upstream dependency is unavailable |

Every error includes the request ID. Error details must not contain secrets, full paper text,
provider prompts, or raw database messages.

## Endpoint Ownership

| Endpoint group | Owner |
|---|---|
| health, papers, preferences, events, graph, jobs | Ruiyu |
| paper summary, Q&A, recommended digest | Yifan |

The endpoint list and schemas are frozen at the end of Milestone 1. Implementation details,
model choices, and ranking parameters may evolve without changing the public contract.
