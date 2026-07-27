#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
EVALUATION_DIR="$REPO_ROOT/docs/evaluation/live-core"
RAW_DIR="$EVALUATION_DIR/raw"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
LIVE_BASE_URL="${MNEME_LIVE_CORE_BASE_URL:-}"
LIVE_TOKEN="${MNEME_LIVE_CORE_TOKEN:-}"
LIVE_SEED="${MNEME_LIVE_CORE_SEED:-1706.03762}"
LIVE_QUESTION="${MNEME_LIVE_CORE_QUESTION:-What problem does this paper address, and what method does it propose?}"
LIVE_QUESTION_BASE64="$(printf '%s' "$LIVE_QUESTION" | base64 | tr -d '\n')"
DEVICE_OUTPUT="/sdcard/Android/data/com.mneme.app/files/live-core-evaluation"

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

pull_artifacts() {
    mkdir -p "$RAW_DIR"
    "$ADB" pull "$DEVICE_OUTPUT/." "$RAW_DIR/" >/dev/null 2>&1 || true
}

trap pull_artifacts EXIT

[[ -x "$ADB" ]] || fail "adb was not found under $ANDROID_SDK_ROOT."
[[ -x "$JAVA_HOME/bin/java" ]] || fail "JDK 17 was not found under $JAVA_HOME."
command -v jq >/dev/null || fail "jq is required to write the run manifest."
command -v base64 >/dev/null || fail "base64 is required to pass the fixed question safely."
[[ -n "$LIVE_BASE_URL" ]] ||
    fail "Set MNEME_LIVE_CORE_BASE_URL to the emulator-visible backend /v1/ URL."
[[ -n "$LIVE_TOKEN" ]] ||
    fail "Set MNEME_LIVE_CORE_TOKEN to the raw demo token; it is never written to artifacts."

device_count="$("$ADB" devices | awk 'NR > 1 && $2 == "device" { count += 1 } END { print count + 0 }')"
[[ "$device_count" -eq 1 ]] || fail "Exactly one ready Android device or emulator is required."

git -C "$REPO_ROOT" diff --quiet ||
    fail "Commit or stash tracked changes before recording thesis measurements."
git -C "$REPO_ROOT" diff --cached --quiet ||
    fail "Commit or unstage staged changes before recording thesis measurements."

rm -rf "$RAW_DIR"
mkdir -p "$RAW_DIR"
"$ADB" shell rm -rf "$DEVICE_OUTPUT"

jq -n \
    --arg schema_version "live-core-run-manifest-v1" \
    --arg measured_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg repository_revision "$(git -C "$REPO_ROOT" rev-parse HEAD)" \
    --arg branch "$(git -C "$REPO_ROOT" branch --show-current)" \
    --arg backend_url "$LIVE_BASE_URL" \
    --arg seed_arxiv_id "$LIVE_SEED" \
    --arg question "$LIVE_QUESTION" \
    --arg summary_model "${MNEME_LLM_SUMMARY_MODEL:-not-recorded}" \
    --arg qa_model "${MNEME_LLM_QA_MODEL:-not-recorded}" \
    --arg embedding_backend "${MNEME_AI_EMBEDDING_BACKEND:-not-recorded}" \
    --arg embedding_model "${MNEME_AI_EMBEDDING_MODEL:-not-recorded}" \
    '{
        schema_version: $schema_version,
        measured_at_utc: $measured_at_utc,
        repository_revision: $repository_revision,
        branch: $branch,
        live_backend_url: $backend_url,
        fixed_seed_arxiv_id: $seed_arxiv_id,
        fixed_free_form_question: $question,
        ui_iterations: 1,
        repository_iterations: 5,
        backend_ai_configuration: {
            summary_model: $summary_model,
            qa_model: $qa_model,
            embedding_backend: $embedding_backend,
            embedding_model: $embedding_model
        },
        live_token_retained: false,
        interpretation: "Acceptance and repeated-path evidence; timings are descriptive and mix cold preparation with durable/cache reuse."
    }' \
    >"$RAW_DIR/run_manifest.json"

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
"$ADB" shell pm clear --user 0 com.mneme.app >/dev/null

instrument_output="$RAW_DIR/instrumentation_output.txt"
set +e
"$ADB" shell am instrument \
    -w \
    -r \
    --user 0 \
    -e class \
    com.mneme.app.evaluation.LiveCoreProductPathTest \
    -e liveCoreBaseUrl \
    "$LIVE_BASE_URL" \
    -e liveCoreToken \
    "$LIVE_TOKEN" \
    -e liveCoreSeed \
    "$LIVE_SEED" \
    -e liveCoreQuestionBase64 \
    "$LIVE_QUESTION_BASE64" \
    com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner \
    | tee "$instrument_output"
instrument_status="${PIPESTATUS[0]}"
set -e

pull_artifacts
[[ "$instrument_status" -eq 0 ]] ||
    fail "Android instrumentation returned exit status $instrument_status."
grep -q '^OK (1 test)' "$instrument_output" ||
    fail "Android instrumentation did not report one passing live-core test."
[[ -s "$RAW_DIR/live_core_path.csv" ]] ||
    fail "Android instrumentation did not produce live_core_path.csv."

trap - EXIT
"$ADB" shell am force-stop com.mneme.app
printf 'Live-core raw artifacts written to %s\n' "$RAW_DIR"
