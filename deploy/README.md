# Mneme production operations

This directory contains a conservative, provider-neutral deployment package for one Linux host with systemd and Nginx. It is source code and staging material, not evidence that a cloud host, DNS name, certificate, provider account, or production data set already exists. The deployment owner must review and install the rendered files on the selected host.

## Included artifacts

`templates/` contains an environment skeleton, Nginx bootstrap and TLS configurations, long-running API and ARQ worker services, migration/bootstrap/preflight units, manual seed and MVP smoke services, and timers for ingestion, briefing generation, backups, and private health checks. The renderer accepts only bounded non-secret values and writes a complete deterministic staging tree without installing privileged files.

The API uses Gunicorn with the separately maintained `uvicorn-worker` package, binds only to `127.0.0.1`, and trusts forwarded headers only from the local Nginx peer. The systemd units use a dedicated unprivileged account and restrictive filesystem settings. These defaults still require host-level firewall, TLS, package, secret, and directory ownership decisions.

## 1. Render a staging tree

From the repository root, install the locked backend environment and render files into a non-privileged staging directory:

```bash
uv sync --project backend --locked
uv run --project backend python -m mneme.cli.render_deployment \
  --server-name api.example.edu \
  --output-dir /tmp/mneme-deployment
```

The command emits `deployment-render-v1` JSON. Review every rendered file before installation. Replace every active angle-bracket placeholder in `backend.env`; the static preflight rejects placeholders in required database and model settings. Commented provider, smoke-question, and upload-hook examples may remain disabled until their corresponding path is configured. Provider keys, model IDs, the final hostname, and host paths are operator inputs rather than repository defaults.

Use the renderer flags when the installation differs from the defaults of `/opt/mneme`, `/etc/mneme/backend.env`, `/var/lib/mneme/papers`, `/var/backups/mneme`, user/group `mneme`, port `8000`, or two API workers. The renderer intentionally does not create accounts, install packages, write `/etc`, alter the firewall, request certificates, or enable services.

## 2. Prepare host-owned inputs

The deployment owner must install Python 3.11-3.13, compatible PostgreSQL client tools, Nginx, Redis, and a PostgreSQL 16 database with pgvector. Install this checkout and its locked backend virtual environment at the rendered installation path, create the `mneme` service account (or render another name), and give that account write access only to the paper, state, and backup directories required by the units.

Install the reviewed environment file as a root-owned `0600` file; systemd reads this file when it prepares each service. Generate an opaque demo token, store only its SHA-256 digest in `MNEME_DEMO_TOKEN_SHA256`, and install the raw token separately as `/etc/mneme/demo.token`. The seed and smoke processes read that token after switching to the service account, so the raw-token file must be owned by that account and remain mode `0600`. Do not place the raw value in Git, Android source, shell history, logs, or screenshots.

Backups use libpq indirection so database credentials never appear in process arguments. Create `/etc/mneme/pg_service.conf` with a service named `mneme-backup` and `/etc/mneme/pgpass` with the matching credential. Both files are opened by processes running as the service account, so make them service-account-owned regular files with owner-only permissions. Select a retention count and an off-host encrypted storage policy before claiming disaster recovery readiness.

Run only the Nginx bootstrap configuration on port 80 while obtaining a certificate. After certificate issuance, disable or remove that bootstrap site before enabling the rendered TLS site; leaving both enabled creates duplicate `server_name` listeners. Confirm that only the TLS site is active, run the host's `nginx -t`, and reload Nginx. Non-loopback smoke targets reject plain HTTP. The rendered TLS proxy permits 15 minutes for a response, covering the seed-onboarding route's 12-minute initialization wait with three minutes for request handling and proxy overhead.

## 3. Install and start services

Install the rendered `*.service` and `*.timer` files in the host's systemd unit directory and run `systemctl daemon-reload`. The API and worker require a successful migration, while production preflight is an explicit operator gate. Run it before exposing either long-running service:

```text
database migration -> demo identity bootstrap -> manual production preflight -> API and worker
```

Starting `mneme-preflight.service` triggers bootstrap and migration through its own dependencies. It checks production-safe settings, loopback binding, rendered service-timeout envelopes, demo identity, usable provider credentials, non-placeholder database settings, writable artifact storage, current Alembic head, pgvector, Redis, ordinary-role connection capacity after both PostgreSQL reserve classes, PostgreSQL backup tools, private libpq credentials, and a restart-scoped fingerprint proving that the backup service reaches the application database. The worker job timeout must be at least the model-call timeout plus 30 seconds for bounded post-provider bookkeeping, and cannot exceed 300 seconds because the worker unit reserves the remaining 60 seconds of its stop envelope for graceful shutdown. The optional `--offline` CLI mode validates configuration only, reports `incomplete`, and exits nonzero; it is never a deployment-ready result. The API and worker intentionally do not depend on preflight at runtime, which keeps liveness and readiness behavior separate; the operator must stop when this manual gate fails.

After a passing preflight, enable and inspect both units:

```bash
sudo systemctl start mneme-preflight.service
sudo systemctl enable --now mneme-api.service mneme-worker.service
sudo systemctl status mneme-api.service mneme-worker.service
sudo journalctl -u mneme-preflight.service -u mneme-api.service -u mneme-worker.service
```

Do not paste full environment files, tokens, provider responses, or private database diagnostics into shared logs or issue comments.

## 4. Prepare replayable demo data

Validate the packaged plan without PostgreSQL, Redis, the API, or external providers:

```bash
uv run --project backend python -m mneme.cli.seed_demo --dry-run
```

On the host, the manual service bootstraps the configured user idempotently, invokes seed onboarding for arXiv `1706.03762`, requires the original seed to reach `ready` and all five returned briefing papers to reach the usable `ready` or `partial` state, replaces explicit preferences, and posts deterministic behavior events:

```bash
sudo systemctl start mneme-seed.service
sudo journalctl -u mneme-seed.service
```

The successful `demo-seed-result-v1` record includes `seed_paper_id`, `digest_paper_ids`, `digest_arxiv_ids`, and separate counts for candidates in `ready` and permanent degraded `partial` states; `processing` remains non-terminal until required summary and embedding artifacts finish. Retain the sanitized result and copy `seed_paper_id` into `MNEME_MVP_SMOKE_PAPER_ID` before the smoke run. Reruns on the same installation reuse the onboarding result and stable manifest event UUIDs, reclaim only failed jobs whose current pipeline and artifact/model identities still match, reload the persisted briefing after recovery so returned paper states are current, and require the persisted `demo_seed` event set to match the manifest exactly. This is installation-local replay, not a frozen cross-host data set: the five onboarding candidates and provider-generated summaries, embeddings, answers, and graph observations may vary with live provider state. The manifest fabricates none of those artifacts. Changing a manifest alone does not rotate an existing onboarding digest; use an intentionally new demo identity or an approved reset procedure when the candidate set or event anchor must change.

## 5. Run the public MVP acceptance gate

After TLS and seeding succeed, run the public-API smoke service:

```bash
sudo systemctl start mneme-smoke.service
sudo journalctl -u mneme-smoke.service
```

The `mvp-smoke-report-v1` result verifies public liveness and readiness, authenticated preferences, the seeded catalog paper, asynchronous summary recovery through `GET /v1/jobs/{job_id}`, exact summary-paper identity, a non-empty recommended briefing, and a connected citation graph centered on that paper. Q&A runs only when `MNEME_MVP_SMOKE_QUESTION` is configured; a passing report with that step marked `skipped` does not validate the provider-backed Q&A path. A passing Q&A step requires every source-matched citation to carry the tested paper's UUID and arXiv identity. The runner outputs only bounded counts, status values, operation identifiers, and HTTP status codes, never tokens or response bodies.

The same runner can be invoked from a trusted workstation. Prefer a private token file because a command-line token would be visible in the process list:

```bash
export MNEME_MVP_SMOKE_BASE_URL=https://api.example.edu
export MNEME_MVP_SMOKE_SEED=1706.03762
export MNEME_MVP_SMOKE_PAPER_ID='<seed_paper_id from demo-seed-result-v1>'
export MNEME_MVP_SMOKE_QUESTION='What problem does this paper address, and what method does it propose?'
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

The private health check expects a fresh backup plus recent successful ingestion-stage and digest-stage jobs. These stage-wide timestamps can also be refreshed by manual work, so they do not prove that either systemd timer fired. The check also fails on undispatched, stale-dispatched, or stale-running pipeline work. Trigger the two schedulers, allow the worker to finish their durable jobs, inspect `platform-operations-v1`, and only then validate health:

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

Retain the `systemctl list-timers` output separately; stage freshness and timer activation are complementary acceptance evidence.

The digest timer invokes the weekly scheduler each day so a missed Monday dispatch can recover without creating duplicate briefings; the durable job identity remains scoped to one user and UTC week.

The health unit deliberately leaves `OnFailure` commented. The deployment owner must select and validate a Feishu or provider-specific alert adapter, then force one controlled failure to prove delivery. A green local unit without a tested alert path is not end-to-end monitoring evidence.

## Acceptance record

Record only sanitized outputs and host facts needed for reproducibility: rendered-file review, package versions, migration head, pgvector version, preflight status, systemd/Nginx validation, seed manifest ID and hash, smoke report, backup manifest, isolated restore result, timer state, and alert-delivery result. Keep host addresses, credentials, raw model responses, and private paths out of public artifacts.

The repository supplies the implementation and verification tools. Cloud-provider selection, VM/DNS/firewall provisioning, certificate lifecycle, real API credentials and model selection, off-host backup storage, alert delivery, Android-to-live-backend configuration, physical-device validation, and final evidence capture remain live integration responsibilities.
