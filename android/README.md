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
