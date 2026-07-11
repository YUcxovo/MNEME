# API Contract Governance

The executable OpenAPI document is `openapi-v0.1.yaml`. It is the contract between the
Android and backend sub-teams until FastAPI becomes the generated source of truth.

## Ownership

- DRI: Ruiyu Jiang (shared API contract, middleware, non-AI endpoints)
- AI endpoint owner: Yifan Zhang (`summary`, `qa`, `recommended`)
- Android reviewer: Hanyang Wang (DTO compatibility and mock-client usability)
- Data-model reviewer: Yifan reviews AI/RAG fields; Ruiyu approves persistence impact

Any breaking change requires Ruiyu, the endpoint owner, and Hanyang to approve the PR.
After the FastAPI scaffold exists, CI exports `openapi.json` and compares it with the
committed contract. Breaking changes require a new API version or an explicit coordinated
migration.

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

## Endpoint Ownership

| Endpoint group | Owner |
|---|---|
| health, papers, preferences, events, graph, jobs | Ruiyu |
| paper summary, Q&A, recommended digest | Yifan |

The endpoint list and schemas are frozen at the end of Milestone 1. Implementation details,
model choices, and ranking parameters may evolve without changing the public contract.
