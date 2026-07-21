# Mneme Android

The Android client uses Kotlin, Jetpack Compose, and Material 3.

## Requirements

- JDK 17
- Android SDK 35

## Build

```bash
./gradlew assembleDebug
./gradlew test
./gradlew ktlintCheck detekt lintDebug
```

Copy `local.properties.example` to `local.properties` and set your local Android SDK path when `ANDROID_HOME` is not configured.

## Skeletal product demo

The debug app currently provides one deterministic end-to-end path:

1. Open the daily briefing.
2. Select the seeded paper.
3. Review its structured summary and source.
4. Open the paper Q&A view.
5. Follow the cited source link.

The content comes from `SeededSkeletalContentRepository` and is clearly labelled in the UI as controlled demo data. It does not make a live model call. Keeping the data behind `SkeletalContentRepository` lets a later network-backed implementation replace the seed data without changing the screens or navigation flow.

The presentation follows the team UI/UX prototype: deep navy surfaces, warm gold actions, serif research headings, compact source cards, and cited Q&A bubbles. Prototype-only routes such as Search and Graph remain hidden until their behavior is implemented.

## Local platform status

- Room schema version 3 stores papers, digests, preferences, and cache-refresh metadata; explicit 1 -> 2 -> 3 migrations and exported schemas are committed.
- `OfflineCacheRepository` retains recent briefing content for 14 days and opened papers for 30 days, and records the last successful refresh time.
- DataStore persists explicit local interests/settings. `DigestSyncScheduler` configures unique constrained periodic work, but `DigestSyncWorker` is still a no-op until the network repository exists.
- `DigestNotifier` and the notification channel are implemented, but Android 13+ permission-request UX, API-driven refresh, deep-link routing, and reliability validation remain unfinished.

The client currently has no Retrofit/OkHttp service, Hilt graph, production ViewModels, or backend authentication configuration. Treat the current app as an inspectable local demo and UI/infrastructure baseline rather than a live end-to-end product.
