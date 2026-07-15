# ADR 0001: Pre-Provisioned Demo Token for MVP Authentication

- Status: accepted
- Date: 2026-07-11
- DRI: Ruiyu Jiang

## Decision

The MVP uses one pre-provisioned opaque demo token supplied as
`Authorization: Bearer <token>`. The backend stores only a hash and maps it to the demo
user. There is no login endpoint, registration, password, JWT, refresh token, or account
recovery flow.

The token hash and demo-user UUID are supplied through environment settings. A FastAPI security
dependency hashes the presented token, compares digests in constant time, and returns only the
configured user UUID. This keeps route exemptions explicit and emits the Bearer scheme in generated
OpenAPI. An idempotent bootstrap command creates that user and its initial preferences; schema
migrations never contain a plaintext token.

The token is injected through local/CI secrets and must not be committed or hard-coded in
the production Android source. A mock build may use a non-secret local-development token.

## Rationale

Authentication is not Mneme's research contribution. This design protects endpoints and
keeps a future migration path without spending the 20-day MVP schedule on identity flows.

## Consequences

- Multi-user public deployment is not supported.
- Token validation does not require a database query, but protected user endpoints still fail
  with `user_not_found` until the configured user has been bootstrapped.
- The demo token must be rotated if exposed.
- A future production release requires a separate authentication ADR and API versioning
  review.
