# Mneme Android

The Android client uses Kotlin, Jetpack Compose, Material 3, MVVM, Retrofit/OkHttp,
kotlinx.serialization, Room, DataStore, and WorkManager.

## Requirements

- JDK 17
- Android SDK 35 or newer
- A running Mneme backend for the live skeletal path

When `ANDROID_HOME` is not configured, create the ignored `local.properties` file with
your Android SDK path, for example `sdk.dir=/home/user/Android/Sdk`.

## Build and checks

```bash
./gradlew assembleDebug
./gradlew test
./gradlew ktlintCheck detekt lintDebug
./gradlew connectedDebugAndroidTest
```

## Live skeletal product demo

The configured debug app now exercises the README's skeletal tier across Android and the
FastAPI backend:

1. Read the authenticated demo user's topics.
2. Request the current manual recommended briefing and display its ranked papers.
3. Open a paper and request its stored summary.
4. If summary work is still running, poll the public job resource and reload the summary
   after the job succeeds.
5. Enter and submit one paper-scoped question through the backend RAG path.
6. Display the backend's source-match status and citations, then open the arXiv paper.

The UI labels live, cached, and controlled-fixture content separately. It also renders
`matched`, `partial`, `not_checked`, and `insufficient_evidence` states without claiming
that every answer or summary is verified.

### Configure the Android client

The app reads these values at build time. The priority is Gradle project property,
environment variable, ignored `local.properties`, then the documented default:

- `MNEME_API_BASE_URL`: defaults to `http://10.0.2.2:8000/v1/` for an Android emulator.
- `MNEME_DEMO_TOKEN`: the raw opaque token whose SHA-256 digest is configured by the
  backend.

The base URL must end in `/v1/`. For a persistent local emulator setup, add these lines
to the ignored `local.properties` file alongside `sdk.dir`:

```properties
MNEME_API_BASE_URL=http://10.0.2.2:8000/v1/
MNEME_DEMO_TOKEN=<raw-demo-token>
```

An environment-based one-off build is also supported:

```bash
export MNEME_API_BASE_URL=http://10.0.2.2:8000/v1/
export MNEME_DEMO_TOKEN='<raw-demo-token>'
./gradlew installDebug
```

For a physical device, use a reachable HTTPS endpoint or the development machine's LAN
address instead of `10.0.2.2`. Cleartext HTTP is enabled only by the debug manifest.

Never commit the raw token. Build-time injection keeps it out of source control, but the
MVP token is still extractable from a debug APK and must be treated as a rotatable demo
credential rather than production authentication.

### Prepare the backend

Follow [`../backend/README.md`](../backend/README.md) to configure PostgreSQL/pgvector,
Redis, the demo identity, provider credentials, migrations, API, and ARQ worker. The live
path needs at least one ingested paper with completed summary and embedding stages for the
full briefing -> summary -> Q&A sequence. Process several papers for a representative
ranked briefing rather than limiting normal demo setup to a one-record smoke test.

After PostgreSQL and Redis are running, prepare the configured identity once:

```bash
cd ../backend
uv sync --locked --dev
uv run alembic upgrade head
uv run python -m mneme.cli.bootstrap_demo_user
```

Run the API and worker in separate terminals:

```bash
cd ../backend
uv run uvicorn mneme.main:app --reload
uv run arq mneme.tasks.worker.WorkerSettings
```

With the worker running, schedule a bounded current paper set and follow its durable stages
in the worker log:

```bash
uv run python -m mneme.tasks.fetch_daily --category cs.AI --max-results 5
```

The command is idempotent for each category and UTC date. Once the papers reach `ready` or
`partial` with current summaries, the app's manual recommended-briefing request can rank
and include them. Repeated app launches reuse a fresh manual briefing for 24 hours; this
keeps the visible list stable instead of randomly changing it on every launch.

The Android token must be the raw value whose digest is stored in
`MNEME_DEMO_TOKEN_SHA256`. The app never logs the token and does not send it to the public
health route.

### Controlled fallback

When `MNEME_DEMO_TOKEN` is blank, the app deliberately uses
`SeededSkeletalContentRepository`. The UI identifies this as controlled fixture data and
states that no live backend or model call is made. This mode keeps previews, UI tests, and
an offline presentation path deterministic; it is not evidence of backend integration.

When a token is configured, a failed live briefing refresh uses Room only if a previous
backend briefing exists, and labels that content as cached. With no cache, the app shows a
retryable error instead of silently substituting the fixture. Paper metadata follows the
same policy. Generated Q&A answers are not persisted locally.

## Current client boundaries

- Room schema version 3 stores paper metadata, digest cache payloads, preferences, and
  refresh metadata. The integration reuses the existing schema and migrations.
- The default Activity uses a production `MnemeViewModel` and a manually constructed
  application container. Hilt remains a target-stack choice rather than a dependency of
  this feature unit.
- `OfflineCacheRepository` still retains recent briefing content for 14 days and opened
  papers for 30 days.
- DataStore persists explicit local settings. The existing WorkManager worker remains a
  no-op; live background digest refresh and notification permission UX are not part of the
  skeletal path.
- Saved papers, behavior-event upload, search, graph exploration, login/JWT, FCM, and
  production deployment are outside this integration unit.

The Retrofit DTOs follow [`../docs/api/openapi-v0.1.yaml`](../docs/api/openapi-v0.1.yaml).
No API or database schema change is introduced by the Android integration.
