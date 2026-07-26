#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
RAW_DIR="$REPO_ROOT/docs/evaluation/e4/raw"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
LIVE_BASE_URL="${MNEME_E4_LIVE_BASE_URL:-}"
LIVE_TOKEN="${MNEME_E4_LIVE_TOKEN:-}"

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

[[ -x "$ADB" ]] || fail "adb was not found under $ANDROID_SDK_ROOT."
[[ -x "$JAVA_HOME/bin/java" ]] || fail "JDK 17 was not found under $JAVA_HOME."
command -v jq >/dev/null || fail "jq is required to write the run manifest."
[[ -n "$LIVE_BASE_URL" ]] ||
    fail "Set MNEME_E4_LIVE_BASE_URL to the emulator-visible backend /v1/ URL."
[[ -n "$LIVE_TOKEN" ]] ||
    fail "Set MNEME_E4_LIVE_TOKEN to the raw demo token; it is never written to artifacts."

device_count="$("$ADB" devices | awk 'NR > 1 && $2 == "device" { count += 1 } END { print count + 0 }')"
[[ "$device_count" -eq 1 ]] || fail "Exactly one ready Android device or emulator is required."

git -C "$REPO_ROOT" diff --quiet ||
    fail "Commit or stash tracked changes before recording thesis measurements."
git -C "$REPO_ROOT" diff --cached --quiet ||
    fail "Commit or unstage staged changes before recording thesis measurements."

mkdir -p "$RAW_DIR"
find "$RAW_DIR" -mindepth 1 -maxdepth 1 -type f -delete
"$ADB" shell rm -rf /sdcard/Android/data/com.mneme.app/files/e4-evaluation

(
    cd "$ANDROID_DIR"
    ANDROID_HOME="$ANDROID_SDK_ROOT" \
        ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
        JAVA_HOME="$JAVA_HOME" \
        ./gradlew \
        ktlintCheck \
        detekt \
        lintDebug \
        testDebugUnitTest \
        assembleDebug \
        assembleDebugAndroidTest
)

"$ADB" install -r "$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk" >/dev/null
"$ADB" install -r \
    "$ANDROID_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk" >/dev/null
"$ADB" shell pm clear com.mneme.app >/dev/null

startup_file="$RAW_DIR/app_start_measurements.csv"
printf '%s\n' \
    'track,scenario,iteration,launch_state,total_time_ms,wait_time_ms,success,outcome' \
    >"$startup_file"

measure_launch_pair() {
    local iteration="$1"
    local record="$2"
    local cold_output
    local warm_output
    local cold_state
    local cold_total
    local cold_wait
    local warm_state
    local warm_total
    local warm_wait

    "$ADB" shell am force-stop com.mneme.app
    cold_output="$("$ADB" shell am start -W -n com.mneme.app/.MainActivity)"
    cold_state="$(awk -F': ' '$1 == "LaunchState" { print $2 }' <<<"$cold_output")"
    cold_total="$(awk -F': ' '$1 == "TotalTime" { print $2 }' <<<"$cold_output")"
    cold_wait="$(awk -F': ' '$1 == "WaitTime" { print $2 }' <<<"$cold_output")"

    "$ADB" shell input keyevent 3
    sleep 0.2
    warm_output="$("$ADB" shell am start -W -n com.mneme.app/.MainActivity)"
    warm_state="$(awk -F': ' '$1 == "LaunchState" { print $2 }' <<<"$warm_output")"
    warm_total="$(awk -F': ' '$1 == "TotalTime" { print $2 }' <<<"$warm_output")"
    warm_wait="$(awk -F': ' '$1 == "WaitTime" { print $2 }' <<<"$warm_output")"

    if [[ "$record" == "true" ]]; then
        printf 'startup,cold_process,%s,%s,%s,%s,%s,%s\n' \
            "$iteration" \
            "$cold_state" \
            "$cold_total" \
            "$cold_wait" \
            "$([[ -n "$cold_wait" ]] && printf true || printf false)" \
            'controlled_fixture_activity_visible' \
            >>"$startup_file"
        printf 'startup,warm_task_resume,%s,%s,%s,%s,%s,%s\n' \
            "$iteration" \
            "$warm_state" \
            "$warm_total" \
            "$warm_wait" \
            "$([[ -n "$warm_wait" ]] && printf true || printf false)" \
            'controlled_fixture_activity_visible' \
            >>"$startup_file"
    fi
    "$ADB" shell input keyevent 3
}

for warmup in 1 2 3; do
    measure_launch_pair "$warmup" false
done
for iteration in $(seq 1 20); do
    measure_launch_pair "$iteration" true
done

"$ADB" shell am instrument \
    -w \
    -r \
    -e class \
    com.mneme.app.evaluation.E4StateMeasurementTest,com.mneme.app.evaluation.E4EventSyncMeasurementTest,com.mneme.app.ui.graph.E4GraphMeasurementTest \
    com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner

"$ADB" shell am instrument \
    -w \
    -r \
    -e class \
    com.mneme.app.evaluation.E4LiveBackendClosedLoopTest \
    -e e4BaseUrl \
    "$LIVE_BASE_URL" \
    -e e4Token \
    "$LIVE_TOKEN" \
    com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner

"$ADB" pull \
    /sdcard/Android/data/com.mneme.app/files/e4-evaluation/. \
    "$RAW_DIR/" \
    >/dev/null

jq -n \
    --arg schema_version "e4-run-manifest-v1" \
    --arg measured_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg repository_revision "$(git -C "$REPO_ROOT" rev-parse HEAD)" \
    --arg branch "$(git -C "$REPO_ROOT" branch --show-current)" \
    --arg backend_url "$LIVE_BASE_URL" \
    --arg startup_mode "blank-token controlled fixture" \
    '{
        schema_version: $schema_version,
        measured_at_utc: $measured_at_utc,
        repository_revision: $repository_revision,
        branch: $branch,
        live_backend_url: $backend_url,
        startup_mode: $startup_mode,
        live_token_retained: false
    }' \
    >"$RAW_DIR/run_manifest.json"

"$ADB" shell am force-stop com.mneme.app
printf 'E4 raw artifacts written to %s\n' "$RAW_DIR"
