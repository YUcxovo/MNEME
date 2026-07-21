# Changelog

All notable changes to Mneme will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added a Retrofit/OkHttp Android integration for the authenticated skeletal path across
  preferences, manual recommended briefings, paper metadata, async summaries/jobs, and
  user-entered single-paper Q&A.
- Added MVVM loading/error/job-polling state, explicit live/cached/controlled-fixture UI
  disclosure, and Room-backed briefing and paper metadata fallback without a schema bump.
- Added Android network contract, repository fallback, and Room cache round-trip tests.
- Added opt-in DeepSeek generation and local BGE Small/FastEmbed embedding providers with
  explicit model provenance, zero-cost local vectors, and no API or schema change.
- Added an Android skeletal-demo flow with type-safe navigation, controlled research
  content, inspectable paper details, and a source-visible single-paper Q&A path.
- Added Android Room/DataStore local foundations, explicit Room migrations through schema version 3, offline cache metadata and retention policies, a WorkManager scheduling stub, and local research-briefing notification primitives.
- Added a buildable Android application scaffold with Jetpack Compose, Material 3, lint,
  static-analysis, and unit-test tooling.
- Added a FastAPI backend scaffold with environment-backed configuration, structured
  logging, request correlation, and a versioned health endpoint.
- Added async PostgreSQL session infrastructure, a shared SQLAlchemy model base, and an
  Alembic migration environment.
- Added application-scoped Redis infrastructure and a minimal ARQ worker entry point.
- Added backend formatting, linting, type-checking, and base test coverage compatible with
  the repository hooks and CI workflow.
- Added the frozen v0.1 PostgreSQL/pgvector schema and reversible initial Alembic migration.
- Added a serialized, rate-limited arXiv Atom client with safe parsing, retry handling,
  revision-aware metadata persistence, and a standalone ingestion command.
- Added pre-provisioned demo Bearer authentication, bootstrap and token-digest commands,
  validated request IDs, and a shared non-sensitive API error envelope.
- Added authenticated paper list/detail and explicit preference GET/PUT endpoints with
  keyset pagination and idempotent normalized replacement.
- Added provider-agnostic Anthropic/OpenAI completion services with environment-backed model routing, Redis caching, daily budget enforcement, deterministic provider fakes, and QA evaluation seed fixtures.
- Added structured summarization, section-aware chunking, OpenAI embeddings, pgvector retrieval, source-matched single-paper Q&A, recommendation services, and pure knowledge-graph algorithms.
- Added revision-safe PDF download, bounded transport validation, atomic artifact storage, PyMuPDF/pdfplumber extraction, three parse-quality tiers, and abstract-only parser fallback with persisted provenance.
- Added durable revision-scoped pipeline jobs with input-derived identities, PostgreSQL concurrency control, dispatch leases, stable ARQ attempt IDs, retry recovery, and authenticated `GET /jobs/{job_id}` status.
- Added cron-friendly daily arXiv ingestion and weekly Research Briefing schedulers, metadata/document/AI/digest workers, and automatic recovery of stranded revision dispatches.
- Added cursor-paginated persisted Research Briefings and summary-route recovery from the earliest missing download, parse, or summarize stage.
- Added additive migrations for parse provenance, download provenance, and recoverable dispatch leases.
- Added deterministic PostgreSQL/pgvector end-to-end coverage for download, parse, summarize, chunk, embed, weekly digest, and authenticated result APIs.

### Changed

- Replaced unconditional Android source-verification wording with the exact summary/Q&A
  source-match status returned by the backend.
- Aligned the Android skeletal-demo screens with the team UI/UX prototype's navy and gold
  visual system while retaining controlled repository fixtures and inspectable sources.
- Updated Android CI so instrumented-test Gradle commands run from the Android project root.
- Bound summaries, chunks, embeddings, retrieval, Q&A evidence, and digest candidates to exact arXiv revisions instead of paper-level artifacts.

### Fixed

- Preserved logical reading order for multi-column PDFs, added bounded overview evidence to
  single-paper retrieval, and prevented mixed provider refusal markers from discarding cited
  answers. Citation source matching now evaluates each cited local claim instead of penalizing
  multi-source answers as a whole. PDF and legacy sidecar text now drop database-unsafe control
  characters before chunk persistence.
- Prevented current-revision summary and Q&A responses from reusing stale artifacts from an older arXiv revision.
- Decoded PostgreSQL aggregate pgvector values through the vector type before recommendation scoring.
- Aligned generated async-response OpenAPI documentation and optional summary fields with the frozen v0.1 contract.
