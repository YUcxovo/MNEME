# Changelog

All notable changes to Mneme will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added an Android skeletal-demo flow with type-safe navigation, controlled research
  content, inspectable paper details, and a source-visible single-paper Q&A path.
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

### Changed

- Aligned the Android skeletal-demo screens with the team UI/UX prototype's navy and gold
  visual system while retaining controlled repository fixtures and inspectable sources.
