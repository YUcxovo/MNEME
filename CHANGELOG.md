# Changelog

All notable changes to Mneme will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added a buildable Android application scaffold with Jetpack Compose, Material 3, lint,
  static-analysis, and unit-test tooling.
- Added a FastAPI backend scaffold with environment-backed configuration, structured
  logging, request correlation, and a versioned health endpoint.
- Added async PostgreSQL session infrastructure, a shared SQLAlchemy model base, and an
  Alembic migration environment.
- Added application-scoped Redis infrastructure and a minimal ARQ worker entry point.
- Added backend formatting, linting, type-checking, and base test coverage compatible with
  the repository hooks and CI workflow.
