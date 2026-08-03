# Mneme production operations

This directory contains a conservative, provider-neutral deployment package for one Linux host with systemd and Nginx. It is source code and staging material, not evidence that a cloud host, DNS name, certificate, provider account, or production data set already exists. The deployment owner must review and install the rendered files on the selected host.

## Included artifacts

`templates/` contains an environment skeleton, Nginx bootstrap and TLS configurations, long-running API and ARQ worker services, ordered migration/bootstrap/preflight gates, manual seed and MVP smoke services, and timers for ingestion, briefing generation, backups, and private health checks. The renderer accepts only bounded non-secret values and writes a complete deterministic staging tree without installing privileged files.

The API uses Gunicorn with the separately maintained `uvicorn-worker` package, binds only to `127.0.0.1`, and trusts forwarded headers only from the local Nginx peer. The systemd units use a dedicated unprivileged account and restrictive filesystem settings. These defaults still require host-level firewall, TLS, package, secret, and directory ownership decisions.

## 1. Render a staging tree

From the repository root, install the locked backend environment and render files into a non-privileged staging directory:

```bash
uv sync --project backend --locked
uv run --project backend python -m mneme.cli.render_deployment \
  --server-name api.example.edu \
  --output-dir /tmp/mneme-deployment
```

The command emits `deployment-render-v1` JSON. Review every rendered file before installation. Replace every angle-bracket placeholder in `backend.env`; a remaining placeholder makes production preflight fail. Provider keys, model IDs, the final hostname, and host paths are operator inputs rather than repository defaults.

Use the renderer flags when the installation differs from the defaults of `/opt/mneme`, `/etc/mneme/backend.env`, `/var/lib/mneme/papers`, `/var/backups/mneme`, user/group `mneme`, port `8000`, or two API workers. The renderer intentionally does not create accounts, install packages, write `/etc`, alter the firewall, request certificates, or enable services.

## 2. Prepare host-owned inputs

The deployment owner must install Python 3.11-3.13, compatible PostgreSQL client tools, Nginx, Redis, and a PostgreSQL 16 database with pgvector. Install this checkout and its locked backend virtual environment at the rendered installation path, create the service account, and give that account write access only to the paper, state, and backup directories required by the units.

Install the reviewed environment file with mode `0600`. Generate an opaque demo token, store only its SHA-256 digest in `MNEME_DEMO_TOKEN_SHA256`, and install the raw token separately as `/etc/mneme/demo.token` with mode `0600`; do not place the raw value in Git, Android source, shell history, logs, or screenshots.

Backups use libpq indirection so database credentials never appear in process arguments. Create `/etc/mneme/pg_service.conf` with a service named `mneme-backup` and `/etc/mneme/pgpass` with the matching credential, both as regular owner-only files. Select a retention count and an off-host encrypted storage policy before claiming disaster recovery readiness.

Run the Nginx bootstrap configuration on port 80 while obtaining a certificate. After certificate issuance, install the rendered TLS configuration, test it with the host's `nginx -t`, and reload Nginx. Non-loopback smoke targets reject plain HTTP.

## 3. Install and start services

Install the rendered `*.service` and `*.timer` files in the host's systemd unit directory and run `systemctl daemon-reload`. Starting either long-running backend unit enforces this order through systemd dependencies:

```text
database migration -> demo identity bootstrap -> production preflight -> API or worker
```

The preflight gate checks production-safe settings, loopback binding, shutdown headroom, demo identity, provider routing, non-placeholder database settings, writable artifact storage, current Alembic head, pgvector, Redis, database connection capacity, PostgreSQL backup tools, and private libpq backup credentials. A failed check prevents the API and worker units from starting.

After reviewing the dependency chain, start and inspect both units:

```bash
sudo systemctl start mneme-api.service mneme-worker.service
sudo systemctl status mneme-api.service mneme-worker.service
sudo journalctl -u mneme-preflight.service -u mneme-api.service -u mneme-worker.service
```

Do not paste full environment files, tokens, provider responses, or private database diagnostics into shared logs or issue comments.

## 4. Prepare reproducible demo data

Validate the packaged plan without PostgreSQL, Redis, the API, or external providers:

```bash
cd backend
uv run python -m mneme.cli.seed_demo --dry-run
```

On the host, the manual service bootstraps the configured user idempotently, invokes seed onboarding for arXiv `1706.03762`, waits for all five returned briefing papers to reach `ready`, replaces explicit preferences, and posts deterministic behavior events:

```bash
sudo systemctl start mneme-seed.service
sudo journalctl -u mneme-seed.service
```

Immediate reruns reuse the manifest-scoped onboarding digest and event UUIDs. The manifest contains no generated summary, answer, embedding, or fabricated graph edge; those artifacts must come from the configured runtime providers. If the preserved event timestamps age outside the active behavior window, version the manifest and intentionally reset its identities before a later demonstration rather than presenting old events as fresh observations.

## 5. Run the public MVP acceptance gate

After TLS and seeding succeed, run the HTTP-only smoke service:

```bash
sudo systemctl start mneme-smoke.service
sudo journalctl -u mneme-smoke.service
```

The `mvp-smoke-report-v1` result verifies public liveness and readiness, authenticated preferences, the seeded catalog paper, asynchronous summary recovery through `GET /v1/jobs/{job_id}`, a non-empty recommended briefing, and a connected citation graph. Q&A runs only when `MNEME_LIVE_CORE_QUESTION` is configured; a passing report with that step marked `skipped` does not validate the provider-backed Q&A path. The runner outputs only bounded counts, status values, operation identifiers, and HTTP status codes, never tokens or response bodies.

The same runner can be invoked from a trusted workstation. Prefer a private token file because a command-line token would be visible in the process list:

```bash
export MNEME_LIVE_CORE_BASE_URL=https://api.example.edu
export MNEME_LIVE_CORE_SEED=1706.03762
export MNEME_LIVE_CORE_QUESTION='What problem does this paper address, and what method does it propose?'
uv run --project backend python -m mneme.cli.smoke_backend --token-file /absolute/path/demo.token
```

Exit code `0` means every required check passed, `1` means an acceptance check failed, and `2` means local configuration was invalid. Treat Q&A as fully accepted only when the configured production provider/model pair returns a non-empty answer whose citations are all source-matched.

## 6. Validate backup and monitoring before enabling timers

Create the first backup and inspect its `mneme-backup-v1` manifest:

```bash
sudo systemctl start mneme-backup.service
sudo journalctl -u mneme-backup.service
```

The command creates a custom-format `pg_dump`, verifies that `pg_restore --list` can read it, records its SHA-256 and size, and retains only recognized archive/manifest pairs. This is not a restore drill. Before sign-off, the deployment owner must restore an archive into an isolated scratch database, verify application-level records and pgvector data, account separately for local PDF artifacts, and test any off-host upload/encryption hook.

The private health check expects a fresh backup plus recent successful ingestion and digest jobs. Trigger the two schedulers, allow the worker to finish their durable jobs, inspect `platform-operations-v1`, and only then validate health:

```bash
sudo systemctl start mneme-ingest.service mneme-digest.service
sudo systemctl start mneme-health.service
sudo journalctl -u mneme-ingest.service -u mneme-digest.service -u mneme-health.service
```

After one successful manual cycle, enable the four timers:

```bash
sudo systemctl enable --now mneme-ingest.timer mneme-digest.timer
sudo systemctl enable --now mneme-backup.timer mneme-health.timer
sudo systemctl list-timers 'mneme-*'
```

The health unit deliberately leaves `OnFailure` commented. The deployment owner must select and validate a Feishu or provider-specific alert adapter, then force one controlled failure to prove delivery. A green local unit without a tested alert path is not end-to-end monitoring evidence.

## Acceptance record

Record only sanitized outputs and host facts needed for reproducibility: rendered-file review, package versions, migration head, pgvector version, preflight status, systemd/Nginx validation, seed manifest ID and hash, smoke report, backup manifest, isolated restore result, timer state, and alert-delivery result. Keep host addresses, credentials, raw model responses, and private paths out of public artifacts.

The repository supplies the implementation and verification tools. Cloud-provider selection, VM/DNS/firewall provisioning, certificate lifecycle, real API credentials and model selection, off-host backup storage, alert delivery, Android-to-live-backend configuration, physical-device validation, and final evidence capture remain live integration responsibilities.
