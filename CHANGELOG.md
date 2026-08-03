# Changelog

All notable changes to Mneme will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added revision-safe source provenance for summary key claims: deterministic
  post-generation matching against the exact revision's stored chunks, explicit
  unmatched states, provenance recomputation on chunk replacement, and additive
  `claims` fields in the summary API contract.
- Added Android paper sharing with both an app deep link and the paper's real arXiv URL,
  plus `mneme://paper/<backend-paper-UUID>` handling for cold starts and existing app
  tasks through the normal paper repository, including its Room-backed offline fallback.
- Added live Android briefing synchronization with network-constrained periodic work,
  Room cache refresh, digest-identity notification deduplication, and Android 13+ permission-safe delivery.
- Added Android claim-level summary sources with expandable section, page, and excerpt
  details, truthful unavailable states, same-paper source actions, and a Room v5 cache
  migration that preserves source associations across refreshes and process restarts.
- Added separate public liveness and bounded PostgreSQL/Redis readiness probes with safe dependency-status responses.
- Added a bounded SQL-backed `platform-operations-v1` JSON report for jobs, papers, parse quality, and briefing generation without raw failure diagnostics.
- Added Android paper save/share actions backed by the existing durable event queue, plus
  paper-scoped follow-up Q&A that reuses backend conversation identities and retains the
  active conversation on screen.
- Added citation-backed seed onboarding that resolves five arXiv neighbors, persists their
  real Semantic Scholar edges, prepares the seed and returned papers, and preserves the
  existing same-category briefing as an explicit provider-unavailable fallback.
- Added Android explicit-interest editing with validated add, edit, and delete actions,
  frozen-contract preference persistence, briefing refresh, failure recovery, and retained
  client evaluation runners.
- Added Android citation-graph exploration with frozen API binding, a local d3 v7 WebView
  renderer, persistent node selection, and paper-detail navigation.
- Added contract-aligned Android behavioral-event capture for visible paper impressions,
  paper opens, and paper-scoped questions, with a Room-backed retry queue, idempotent
  `POST /events` batches, and network-constrained WorkManager synchronization.
- Added first-run seed-paper onboarding that derives the user's initial arXiv category,
  prepares five related papers through the live backend pipeline, and opens the Android
  briefing only after the complete set is ready.
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
- Added a throttled and retrying Semantic Scholar client, explicit graph-sync CLI, bidirectional citation observation persistence, identity resolution, and bounded local traversal.
- Added authenticated `GET /graph/{paper_id}` with depth/node limits, deterministic algorithm enrichment, and a safe baseline fallback.
- Added deterministic `behavior-v1` aggregation and authenticated idempotent `POST /events` batches with transactional preference recomputation.
- Added PostgreSQL/pgvector end-to-end coverage for event deduplication, exact-revision/model behavior vectors, rollback, bounded citation-graph queries, and unresolved-to-local citation resolution across later graph synchronization.
- Added a confidence-calibrated contrastive behavior model with dual-timescale decay, per-paper saturation, exposure-gated negative feedback, separate positive and negative profiles, inspectable evidence, and bounded confidence while retaining the frozen v1 replay baseline.
- Added migration `0007`, an idempotent raw-event replay command, and version-aware digest generation for the active behavior profile.
- Added a deterministic controlled behavior-evaluation fixture, four headline systems, five mechanism ablations, ranking and diversity metrics, paired fixed-seed bootstrap summaries, sanitized provenance, atomic artifacts, and thesis-ready plotting tools.

### Changed

- Audited bounded pagination and platform query indexes, retaining one evidence-gated failed-job index candidate instead of adding speculative global-aggregate indexes.
- Applied one bounded PostgreSQL connection-pool configuration across the API, worker, schedulers, and standalone backend commands.
- Replaced unconditional Android source-verification wording with the exact summary/Q&A
  source-match status returned by the backend.
- Aligned the Android skeletal-demo screens with the team UI/UX prototype's navy and gold
  visual system while retaining controlled repository fixtures and inspectable sources.
- Updated Android CI so instrumented-test Gradle commands run from the Android project root.
- Bound summaries, chunks, embeddings, retrieval, Q&A evidence, and digest candidates to exact arXiv revisions instead of paper-level artifacts.
- Restricted behavior-based recommendation candidates to the behavior vector's embedding model and invalidated cached manual digests after preference changes.
- Changed recommendation generation to confidence-gate the behavior component, subtract negative similarity through a bounded contrastive affinity, and identify snapshots as `recommender-v2`.

### Fixed

- Made Android deep-link open events replay-safe by carrying one event UUID through
  navigation and using an idempotent Room insertion boundary.
- Preserved citation-backed seed candidates when a temporary arXiv batch failure requires
  smaller metadata requests, and return an explicit retryable error instead of silently
  completing with unrelated papers when their metadata remains unavailable.
- Kept manual recommendation refresh useful for an older seed library by ranking processed
  catalog papers when the configured recent-candidate window is empty.
- Accepted numeric Semantic Scholar external identifiers while retaining string validation
  for arXiv identities, matching the provider's live response format.
- Applied the Mneme theme content color to first-run and blocking onboarding
  states so their title and status text remain readable in dark mode.
- Restored the last complete Room-backed briefing after an Android process restart instead
  of requesting the seed paper again; fresh installs and cleared app data still onboard.
- Preserved logical reading order for multi-column PDFs, added bounded overview evidence to
  single-paper retrieval, and prevented mixed provider refusal markers from discarding cited
  answers. Citation source matching now evaluates each cited local claim instead of penalizing
  multi-source answers as a whole. PDF and legacy sidecar text now drop database-unsafe control
  characters before chunk persistence.
- Rejected behavioral events more than five minutes ahead of the server clock and bounded preference recomputation to the same accepted time range.
- Serialized recommended-digest freshness checks and generation with behavioral preference updates so a concurrently ingested event cannot leave a newly generated stale digest reusable.
- Prevented stale preference-model or generator snapshots from being reused after behavior semantics change.
- Quantized derived vectors to pgvector's storage precision before no-op comparison so deterministic replay does not spuriously update preference freshness.
- Indexed unresolved external citation targets for later provider-identity resolution.
- Prevented current-revision summary and Q&A responses from reusing stale artifacts from an older arXiv revision.
- Decoded PostgreSQL aggregate pgvector values through the vector type before recommendation scoring.
- Aligned generated async-response OpenAPI documentation and optional summary fields with the frozen v0.1 contract.
