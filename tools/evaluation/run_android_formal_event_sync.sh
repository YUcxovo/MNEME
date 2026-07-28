#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
EVALUATION_DIR="$REPO_ROOT/docs/evaluation/android-formal/event-sync"
RAW_ROOT="$EVALUATION_DIR/raw"

ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"

BASE_URL="${MNEME_EVENT_SYNC_BASE_URL:-}"
EVENT_TOKEN="${MNEME_EVENT_SYNC_TOKEN:-}"
PAPER_ID="${MNEME_EVENT_SYNC_PAPER_ID:-}"
MODE="${MNEME_EVENT_SYNC_MODE:-formal}"
ITERATIONS="${MNEME_EVENT_SYNC_ITERATIONS:-10}"
ISOLATION_ACK="${MNEME_EVENT_SYNC_ISOLATED_BACKEND_ACK:-}"
INSTRUMENTATION_TIMEOUT="${MNEME_EVENT_SYNC_TIMEOUT:-15m}"

APP_PACKAGE="com.mneme.app"
TEST_PACKAGE="com.mneme.app.test"
TEST_CLASS="com.mneme.app.evaluation.E4LiveBackendClosedLoopTest"
TEST_RUNNER="androidx.test.runner.AndroidJUnitRunner"
REMOTE_OUTPUT_DIR="/sdcard/Android/data/$APP_PACKAGE/files/e4-evaluation"
RAW_CSV_NAME="formal_event_sync_measurements.csv"
DEVICE_TEST_ENV_NAME="environment.json"
ANALYZER="$SCRIPT_DIR/analyze_android_formal_event_sync.py"
TEST_SOURCE="$ANDROID_DIR/app/src/androidTest/java/com/mneme/app/evaluation/E4LiveBackendClosedLoopTest.kt"

RUN_DIR=""
SERIAL=""
REVISION=""
TREE_REVISION=""
STARTED_AT_UTC=""
INSTRUMENTATION_STARTED_AT_UTC=""
INSTRUMENTATION_ENDED_AT_UTC=""
INSTRUMENTATION_STARTED="false"
INSTRUMENTATION_STATUS="-1"
INSTRUMENTATION_REPORTED_SUCCESS="false"
PULL_STATUS="-1"
FINALIZED="false"
RAW_INSTRUMENTATION_LOG=""
ANDROID_API=""
ANDROID_RELEASE=""
DEVICE_MODEL=""
DEVICE_MANUFACTURER=""
BOOT_ID=""
WEBVIEW_VERSION=""
WEBVIEW_DESCRIPTION=""
HOST_LOAD=""
START_RUNNER_HASH=""
START_ANALYZER_HASH=""
START_TEST_SOURCE_HASH=""
START_ANDROID_CODE_HASH=""
APP_APK_HASH=""
TEST_APK_HASH=""
REPOSITORY_UNCHANGED_AT_FINISH="false"
APP_FORCE_STOPPED_BEFORE_CLEAR="false"
APP_DATA_CLEARED_BEFORE_INSTRUMENTATION="false"

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

sha256_or_empty() {
    local path="$1"
    if [[ -f "$path" ]]; then
        sha256sum "$path" | awk '{ print $1 }'
    else
        printf '\n'
    fi
}

redact_instrumentation_output() {
    local destination="$RUN_DIR/instrumentation_output.txt"
    if [[ ! -f "$RAW_INSTRUMENTATION_LOG" ]]; then
        : >"$destination"
        return
    fi
    MNEME_REDACTION_VALUE="$EVENT_TOKEN" python3 - "$RAW_INSTRUMENTATION_LOG" "$destination" <<'PY'
import os
import pathlib
import sys

source = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
secret = os.environ["MNEME_REDACTION_VALUE"]
payload = source.read_text(encoding="utf-8", errors="replace")
if secret:
    payload = payload.replace(secret, "[REDACTED]")
destination.write_text(payload, encoding="utf-8")
PY
}

redact_saved_text_file() {
    local path="$1"
    [[ -f "$path" ]] || return 0
    MNEME_REDACTION_VALUE="$EVENT_TOKEN" python3 - "$path" <<'PY'
import os
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
secret = os.environ["MNEME_REDACTION_VALUE"]
payload = path.read_text(encoding="utf-8", errors="replace")
if secret:
    payload = payload.replace(secret, "[REDACTED]")
path.write_text(payload, encoding="utf-8")
PY
}

repository_has_only_run_artifacts() {
    local repository_root="$1"
    local expected_revision="$2"
    local allowed_run_dir="$3"
    local relative_run_dir
    local untracked_path

    [[ "$allowed_run_dir" == "$repository_root/"* ]] || return 1
    relative_run_dir="${allowed_run_dir#"$repository_root/"}"
    [[ -n "$relative_run_dir" ]] || return 1
    [[ "$(git -C "$repository_root" rev-parse HEAD 2>/dev/null)" == "$expected_revision" ]] ||
        return 1
    git -C "$repository_root" diff --quiet --ignore-submodules=none -- || return 1
    git -C "$repository_root" diff --cached --quiet --ignore-submodules=none -- || return 1

    while IFS= read -r -d '' untracked_path; do
        [[ "$untracked_path" == "$relative_run_dir/"* ]] || return 1
    done < <(
        git -C "$repository_root" \
            ls-files --others --exclude-standard -z
    )
}

run_repository_guard_self_test() {
    local fixture_root
    local fixture_revision
    local fixture_run_dir

    fixture_root="$(mktemp -d)"
    git -C "$fixture_root" init -q
    git -C "$fixture_root" config user.name "MNEME Evaluation Self-Test"
    git -C "$fixture_root" config user.email "evaluation-self-test@example.invalid"
    printf 'baseline\n' >"$fixture_root/tracked.txt"
    git -C "$fixture_root" add tracked.txt
    git -C "$fixture_root" commit -qm "test: create guard fixture"
    fixture_revision="$(git -C "$fixture_root" rev-parse HEAD)"
    fixture_run_dir="$fixture_root/docs/evaluation/android-formal/event-sync/raw/formal-fixture"
    mkdir -p "$fixture_run_dir"
    printf 'allowed result\n' >"$fixture_run_dir/result.csv"

    if ! repository_has_only_run_artifacts \
        "$fixture_root" "$fixture_revision" "$fixture_run_dir"; then
        rm -rf -- "$fixture_root"
        fail "Repository guard rejected the allowed current-run artifact."
    fi

    printf 'unrelated\n' >"$fixture_root/unrelated.txt"
    if repository_has_only_run_artifacts \
        "$fixture_root" "$fixture_revision" "$fixture_run_dir"; then
        rm -rf -- "$fixture_root"
        fail "Repository guard accepted an unrelated untracked file."
    fi
    rm -f -- "$fixture_root/unrelated.txt"

    printf 'tracked change\n' >>"$fixture_root/tracked.txt"
    if repository_has_only_run_artifacts \
        "$fixture_root" "$fixture_revision" "$fixture_run_dir"; then
        rm -rf -- "$fixture_root"
        fail "Repository guard accepted a tracked source change."
    fi
    git -C "$fixture_root" add tracked.txt
    if repository_has_only_run_artifacts \
        "$fixture_root" "$fixture_revision" "$fixture_run_dir"; then
        rm -rf -- "$fixture_root"
        fail "Repository guard accepted a staged source change."
    fi

    rm -rf -- "$fixture_root"
    printf 'Formal event-sync repository-guard self-test passed.\n'
}

write_manifest() {
    local exit_status="$1"
    local finished_at_utc
    local raw_csv="$RUN_DIR/$RAW_CSV_NAME"
    local device_test_environment="$RUN_DIR/device_test_environment.json"
    local instrumentation_output="$RUN_DIR/instrumentation_output.txt"
    local build_output="$RUN_DIR/build_output.txt"
    local install_output="$RUN_DIR/install_output.txt"
    local runner_hash
    local analyzer_hash
    local test_source_hash
    local raw_csv_hash
    local device_test_environment_hash
    local instrumentation_output_hash
    local build_output_hash
    local install_output_hash
    local environment_hash
    local adb_pull_output_hash

    finished_at_utc="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    runner_hash="$START_RUNNER_HASH"
    analyzer_hash="$START_ANALYZER_HASH"
    test_source_hash="$START_TEST_SOURCE_HASH"
    raw_csv_hash="$(sha256_or_empty "$raw_csv")"
    device_test_environment_hash="$(sha256_or_empty "$device_test_environment")"
    instrumentation_output_hash="$(sha256_or_empty "$instrumentation_output")"
    build_output_hash="$(sha256_or_empty "$build_output")"
    install_output_hash="$(sha256_or_empty "$install_output")"
    environment_hash="$(sha256_or_empty "$RUN_DIR/environment.json")"
    adb_pull_output_hash="$(sha256_or_empty "$RUN_DIR/adb_pull_output.txt")"

    jq -n \
        --arg schema_version "android-formal-event-sync-run-v1" \
        --arg run_id "$(basename "$RUN_DIR")" \
        --arg mode "$MODE" \
        --argjson requested_iterations "$ITERATIONS" \
        --arg started_at_utc "$STARTED_AT_UTC" \
        --arg instrumentation_started_at_utc "$INSTRUMENTATION_STARTED_AT_UTC" \
        --arg instrumentation_ended_at_utc "$INSTRUMENTATION_ENDED_AT_UTC" \
        --arg finished_at_utc "$finished_at_utc" \
        --arg repository_revision "$REVISION" \
        --arg repository_tree "$TREE_REVISION" \
        --arg branch "$(git -C "$REPO_ROOT" branch --show-current)" \
        --arg backend_base_url "$BASE_URL" \
        --arg paper_id "$PAPER_ID" \
        --arg serial "$SERIAL" \
        --arg android_api "$ANDROID_API" \
        --arg android_release "$ANDROID_RELEASE" \
        --arg device_model "$DEVICE_MODEL" \
        --arg device_manufacturer "$DEVICE_MANUFACTURER" \
        --arg boot_id "$BOOT_ID" \
        --arg webview_version "$WEBVIEW_VERSION" \
        --arg webview_description "$WEBVIEW_DESCRIPTION" \
        --arg host_load "$HOST_LOAD" \
        --argjson shell_exit_status "$exit_status" \
        --argjson instrumentation_exit_status "$INSTRUMENTATION_STATUS" \
        --argjson instrumentation_reported_success "$INSTRUMENTATION_REPORTED_SUCCESS" \
        --argjson pull_exit_status "$PULL_STATUS" \
        --argjson repository_unchanged_at_finish "$REPOSITORY_UNCHANGED_AT_FINISH" \
        --argjson app_force_stopped_before_clear "$APP_FORCE_STOPPED_BEFORE_CLEAR" \
        --argjson app_data_cleared_before_instrumentation "$APP_DATA_CLEARED_BEFORE_INSTRUMENTATION" \
        --arg runner_sha256 "$runner_hash" \
        --arg analyzer_sha256 "$analyzer_hash" \
        --arg test_source_sha256 "$test_source_hash" \
        --arg android_code_sha256 "$START_ANDROID_CODE_HASH" \
        --arg app_apk_sha256 "$APP_APK_HASH" \
        --arg test_apk_sha256 "$TEST_APK_HASH" \
        --arg raw_csv_sha256 "$raw_csv_hash" \
        --arg device_test_environment_sha256 "$device_test_environment_hash" \
        --arg instrumentation_output_sha256 "$instrumentation_output_hash" \
        --arg build_output_sha256 "$build_output_hash" \
        --arg install_output_sha256 "$install_output_hash" \
        --arg environment_sha256 "$environment_hash" \
        --arg adb_pull_output_sha256 "$adb_pull_output_hash" \
        '{
            schema_version: $schema_version,
            run_id: $run_id,
            mode: $mode,
            requested_iterations: $requested_iterations,
            timestamps: {
                runner_started_utc: $started_at_utc,
                instrumentation_started_utc: $instrumentation_started_at_utc,
                instrumentation_ended_utc: $instrumentation_ended_at_utc,
                runner_finished_utc: $finished_at_utc
            },
            repository: {
                revision: $repository_revision,
                tree: $repository_tree,
                branch: $branch,
                clean_at_start: true,
                unchanged_at_finish: $repository_unchanged_at_finish
            },
            backend: {
                base_url: $backend_base_url,
                paper_id: (if $paper_id == "" then null else $paper_id end),
                isolated_test_instance_acknowledged: true
            },
            android: {
                serial: $serial,
                application_package: "com.mneme.app",
                test_package: "com.mneme.app.test",
                test_class: "com.mneme.app.evaluation.E4LiveBackendClosedLoopTest",
                disposable_measurement_app_data: true,
                force_stopped_before_clear: $app_force_stopped_before_clear,
                app_data_cleared_before_instrumentation: $app_data_cleared_before_instrumentation,
                api: (if $android_api == "" then null else ($android_api | tonumber) end),
                release: (if $android_release == "" then null else $android_release end),
                model: (if $device_model == "" then null else $device_model end),
                manufacturer: (if $device_manufacturer == "" then null else $device_manufacturer end),
                boot_id: (if $boot_id == "" then null else $boot_id end),
                webview_version: (if $webview_version == "" then null else $webview_version end),
                webview_description: (if $webview_description == "" then null else $webview_description end)
            },
            host: {
                loadavg: (if $host_load == "" then null else $host_load end)
            },
            execution: {
                instrumentation_invocations: (if $instrumentation_started_at_utc == "" then 0 else 1 end),
                shell_exit_status: $shell_exit_status,
                instrumentation_exit_status: $instrumentation_exit_status,
                instrumentation_reported_success: $instrumentation_reported_success,
                data_pull_exit_status: $pull_exit_status
            },
            build: {
                jdk_major: 17,
                build_authentication: "blank",
                gradle_tasks: [":app:assembleDebug", ":app:assembleDebugAndroidTest"]
            },
            hashes: {
                runner_sha256: $runner_sha256,
                analyzer_sha256: $analyzer_sha256,
                measured_test_source_sha256: $test_source_sha256,
                android_code_tree_sha256: $android_code_sha256,
                application_apk_sha256: $app_apk_sha256,
                instrumentation_apk_sha256: $test_apk_sha256,
                raw_csv_sha256: $raw_csv_sha256,
                device_test_environment_sha256: $device_test_environment_sha256,
                instrumentation_output_sha256: $instrumentation_output_sha256,
                build_output_sha256: $build_output_sha256,
                install_output_sha256: $install_output_sha256,
                environment_sha256: $environment_sha256,
                adb_pull_output_sha256: $adb_pull_output_sha256
            }
        }' >"$RUN_DIR/run_manifest.json"
}

finalize_run() {
    local exit_status="$1"
    local finalize_status=0

    [[ "$FINALIZED" == "false" ]] || return 0
    FINALIZED="true"
    set +e

    if [[ "$INSTRUMENTATION_STARTED" == "true" ]]; then
        INSTRUMENTATION_ENDED_AT_UTC="${INSTRUMENTATION_ENDED_AT_UTC:-$(date -u +'%Y-%m-%dT%H:%M:%SZ')}"
        redact_instrumentation_output
        grep -Eq '^OK \(1 test\)$' "$RUN_DIR/instrumentation_output.txt"
        if [[ "$?" -eq 0 ]]; then
            INSTRUMENTATION_REPORTED_SUCCESS="true"
        fi

        {
            "$ADB" -s "$SERIAL" pull \
                "$REMOTE_OUTPUT_DIR/$RAW_CSV_NAME" \
                "$RUN_DIR/$RAW_CSV_NAME"
            csv_pull_status="$?"
            "$ADB" -s "$SERIAL" pull \
                "$REMOTE_OUTPUT_DIR/$DEVICE_TEST_ENV_NAME" \
                "$RUN_DIR/device_test_environment.json"
            environment_pull_status="$?"
            [[ "$csv_pull_status" -eq 0 && "$environment_pull_status" -eq 0 ]]
        } >"$RUN_DIR/adb_pull_output.txt" 2>&1
        PULL_STATUS="$?"
        if [[ "$PULL_STATUS" -ne 0 && "$exit_status" -eq 0 ]]; then
            finalize_status=1
        fi
    fi

    if [[ -n "$RUN_DIR" && -d "$RUN_DIR" ]]; then
        if repository_has_only_run_artifacts "$REPO_ROOT" "$REVISION" "$RUN_DIR" &&
            [[ "$(sha256_or_empty "$SCRIPT_DIR/run_android_formal_event_sync.sh")" == "$START_RUNNER_HASH" ]] &&
            [[ "$(sha256_or_empty "$ANALYZER")" == "$START_ANALYZER_HASH" ]] &&
            [[ "$(sha256_or_empty "$TEST_SOURCE")" == "$START_TEST_SOURCE_HASH" ]]; then
            REPOSITORY_UNCHANGED_AT_FINISH="true"
        elif [[ "$exit_status" -eq 0 ]]; then
            finalize_status=1
        fi
        redact_saved_text_file "$RUN_DIR/build_output.txt"
        redact_saved_text_file "$RUN_DIR/install_output.txt"
        redact_saved_text_file "$RUN_DIR/instrumentation_output.txt"
        redact_saved_text_file "$RUN_DIR/adb_pull_output.txt"
        write_manifest "$exit_status" || finalize_status="$?"
    fi
    [[ -z "$RAW_INSTRUMENTATION_LOG" ]] || rm -f -- "$RAW_INSTRUMENTATION_LOG"
    return "$finalize_status"
}

if [[ "${1:-}" == "--self-test" ]]; then
    [[ "$#" -eq 1 ]] || fail "--self-test does not accept additional arguments."
    run_repository_guard_self_test
    exit 0
fi
[[ "$#" -eq 0 ]] || fail "This runner accepts no positional arguments."

on_exit() {
    local exit_status="$?"
    local finalize_status=0

    trap - EXIT
    finalize_run "$exit_status" || finalize_status="$?"
    if [[ "$exit_status" -eq 0 && "$finalize_status" -ne 0 ]]; then
        exit "$finalize_status"
    fi
    exit "$exit_status"
}

trap on_exit EXIT

[[ -x "$ADB" ]] || fail "adb was not found under the configured Android SDK."
[[ -x "$JAVA_HOME/bin/java" ]] || fail "JDK was not found under the configured JAVA_HOME."
command -v git >/dev/null || fail "git is required."
command -v jq >/dev/null || fail "jq is required."
command -v python3 >/dev/null || fail "python3 is required."
command -v sha256sum >/dev/null || fail "sha256sum is required."
command -v timeout >/dev/null || fail "GNU timeout is required."
[[ -f "$ANALYZER" ]] || fail "The formal event-sync analyzer is missing."
[[ -f "$TEST_SOURCE" ]] || fail "The formal event-sync Android test is missing."

java_version="$("$JAVA_HOME/bin/java" -version 2>&1 | head -n 1)"
java_major="$(sed -nE 's/.*version "([0-9]+).*/\1/p' <<<"$java_version")"
[[ "$java_major" == "17" ]] || fail "This measurement requires JDK 17."

[[ -n "$BASE_URL" ]] || fail "Set MNEME_EVENT_SYNC_BASE_URL explicitly."
[[ -n "$EVENT_TOKEN" ]] || fail "Set MNEME_EVENT_SYNC_TOKEN explicitly."
[[ "${#EVENT_TOKEN}" -ge 8 ]] ||
    fail "MNEME_EVENT_SYNC_TOKEN must contain at least eight characters."
[[ "$BASE_URL" == */ ]] || fail "MNEME_EVENT_SYNC_BASE_URL must end with a slash."
[[ "$BASE_URL" =~ ^[A-Za-z0-9:/._~%+-]+$ ]] ||
    fail "MNEME_EVENT_SYNC_BASE_URL contains unsupported shell-sensitive characters."
[[ "$EVENT_TOKEN" =~ ^[-A-Za-z0-9._~+/=]+$ ]] ||
    fail "MNEME_EVENT_SYNC_TOKEN contains unsupported shell-sensitive characters."
[[ "$ISOLATION_ACK" == "isolated-test-backend" ]] ||
    fail "Set MNEME_EVENT_SYNC_ISOLATED_BACKEND_ACK=isolated-test-backend after selecting an isolated test backend."

if ! python3 - "$BASE_URL" "$PAPER_ID" <<'PY'
import sys
import uuid
from urllib.parse import urlsplit

base_url, paper_id = sys.argv[1:]
parsed = urlsplit(base_url)
if parsed.scheme not in {"http", "https"} or not parsed.netloc:
    raise SystemExit("The backend base URL must be an absolute HTTP(S) URL.")
if parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit("The backend base URL cannot contain credentials, a query, or a fragment.")
if paper_id:
    uuid.UUID(paper_id)
PY
then
    fail "MNEME_EVENT_SYNC_BASE_URL or MNEME_EVENT_SYNC_PAPER_ID is invalid."
fi

case "$MODE" in
    formal)
        [[ "$ITERATIONS" == "10" ]] ||
            fail "Formal mode is fixed at exactly 10 batches."
        ;;
    smoke)
        [[ "$ITERATIONS" =~ ^[1-9]$ ]] ||
            fail "Smoke mode requires MNEME_EVENT_SYNC_ITERATIONS from 1 to 9."
        ;;
    *)
        fail "MNEME_EVENT_SYNC_MODE must be formal or smoke."
        ;;
esac

if [[ -n "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
    fail "Formal measurement requires a completely clean Git worktree."
fi
REVISION="$(git -C "$REPO_ROOT" rev-parse HEAD)"
TREE_REVISION="$(git -C "$REPO_ROOT" rev-parse 'HEAD^{tree}')"
START_RUNNER_HASH="$(sha256_or_empty "$SCRIPT_DIR/run_android_formal_event_sync.sh")"
START_ANALYZER_HASH="$(sha256_or_empty "$ANALYZER")"
START_TEST_SOURCE_HASH="$(sha256_or_empty "$TEST_SOURCE")"
START_ANDROID_CODE_HASH="$(
    git -C "$REPO_ROOT" ls-tree -r --full-tree "$REVISION" \
        android/app/src \
        android/app/build.gradle.kts \
        android/gradle/libs.versions.toml |
        sha256sum |
        awk '{ print $1 }'
)"
STARTED_AT_UTC="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
run_timestamp="$(date -u +'%Y%m%dT%H%M%SZ')"
RUN_DIR="$RAW_ROOT/${MODE}-${run_timestamp}-${REVISION:0:12}"
[[ ! -e "$RUN_DIR" ]] || fail "Run artifacts already exist and will not be overwritten: $RUN_DIR"
mkdir -p "$RUN_DIR"
RAW_INSTRUMENTATION_LOG="$(mktemp)"

mapfile -t attached_devices < <("$ADB" devices | awk 'NR > 1 && NF >= 2 { print $1 ":" $2 }')
[[ "${#attached_devices[@]}" -eq 1 ]] ||
    fail "Exactly one Android emulator must be attached."
[[ "${attached_devices[0]}" == emulator-*:device ]] ||
    fail "The only attached Android target must be an online emulator."
SERIAL="${attached_devices[0]%:device}"

export ANDROID_HOME="$ANDROID_SDK_ROOT"
export ANDROID_SDK_ROOT
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$ANDROID_SDK_ROOT/platform-tools:$PATH"

printf 'Building blank-authentication app and instrumentation APKs; output: %s\n' \
    "$RUN_DIR/build_output.txt"
set +e
(
    cd "$ANDROID_DIR"
    ./gradlew \
        :app:assembleDebug \
        :app:assembleDebugAndroidTest \
        -PMNEME_DEMO_TOKEN=
) >"$RUN_DIR/build_output.txt" 2>&1
build_status="$?"
set -e
[[ "$build_status" -eq 0 ]] || fail "Android build failed; the build transcript was preserved."

APP_APK="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
TEST_APK="$ANDROID_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
[[ -f "$APP_APK" ]] || fail "The application APK was not produced."
[[ -f "$TEST_APK" ]] || fail "The instrumentation APK was not produced."
APP_APK_HASH="$(sha256_or_empty "$APP_APK")"
TEST_APK_HASH="$(sha256_or_empty "$TEST_APK")"

mapfile -t attached_devices < <("$ADB" devices | awk 'NR > 1 && NF >= 2 { print $1 ":" $2 }')
[[ "${#attached_devices[@]}" -eq 1 && "${attached_devices[0]}" == "$SERIAL:device" ]] ||
    fail "The emulator set changed during the build."

{
    "$ADB" -s "$SERIAL" install -r -t "$APP_APK"
    "$ADB" -s "$SERIAL" install -r -t "$TEST_APK"
} >"$RUN_DIR/install_output.txt" 2>&1

set +e
"$ADB" -s "$SERIAL" shell am force-stop "$APP_PACKAGE" \
    >>"$RUN_DIR/install_output.txt" 2>&1
force_stop_status="$?"
set -e
[[ "$force_stop_status" -eq 0 ]] ||
    fail "The measurement app could not be force-stopped before clearing its data."
APP_FORCE_STOPPED_BEFORE_CLEAR="true"

set +e
pm_clear_output="$("$ADB" -s "$SERIAL" shell pm clear "$APP_PACKAGE" 2>&1)"
pm_clear_status="$?"
set -e
printf 'pm clear result: %s\n' "$pm_clear_output" >>"$RUN_DIR/install_output.txt"
normalized_pm_clear_output="$(tr -d '\r\n' <<<"$pm_clear_output")"
[[ "$pm_clear_status" -eq 0 && "$normalized_pm_clear_output" == "Success" ]] ||
    fail "The measurement app data could not be cleared."
APP_DATA_CLEARED_BEFORE_INSTRUMENTATION="true"

"$ADB" -s "$SERIAL" shell rm -f \
    "$REMOTE_OUTPUT_DIR/$RAW_CSV_NAME" \
    "$REMOTE_OUTPUT_DIR/$DEVICE_TEST_ENV_NAME"

ANDROID_API="$("$ADB" -s "$SERIAL" shell getprop ro.build.version.sdk | tr -d '\r')"
ANDROID_RELEASE="$("$ADB" -s "$SERIAL" shell getprop ro.build.version.release | tr -d '\r')"
DEVICE_MODEL="$("$ADB" -s "$SERIAL" shell getprop ro.product.model | tr -d '\r')"
DEVICE_MANUFACTURER="$("$ADB" -s "$SERIAL" shell getprop ro.product.manufacturer | tr -d '\r')"
BOOT_ID="$("$ADB" -s "$SERIAL" shell cat /proc/sys/kernel/random/boot_id | tr -d '\r')"
WEBVIEW_DESCRIPTION="$("$ADB" -s "$SERIAL" shell dumpsys webviewupdate | tr -d '\r' | grep -m1 'Current WebView package')"
WEBVIEW_VERSION="$(sed -nE 's/.*\([^,]+, ([^)]+)\).*/\1/p' <<<"$WEBVIEW_DESCRIPTION")"
HOST_LOAD="$(cat /proc/loadavg)"

[[ -n "$ANDROID_API" && -n "$DEVICE_MODEL" && -n "$BOOT_ID" && -n "$WEBVIEW_VERSION" ]] ||
    fail "Required emulator provenance could not be collected."

jq -n \
    --arg collected_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg serial "$SERIAL" \
    --arg android_api "$ANDROID_API" \
    --arg android_release "$ANDROID_RELEASE" \
    --arg device_model "$DEVICE_MODEL" \
    --arg device_manufacturer "$DEVICE_MANUFACTURER" \
    --arg boot_id "$BOOT_ID" \
    --arg webview_version "$WEBVIEW_VERSION" \
    --arg webview_description "$WEBVIEW_DESCRIPTION" \
    --arg host_load "$HOST_LOAD" \
    '{
        schema_version: "android-formal-event-sync-environment-v1",
        collected_at_utc: $collected_at_utc,
        emulator: {
            serial: $serial,
            android_api: ($android_api | tonumber),
            android_release: $android_release,
            model: $device_model,
            manufacturer: $device_manufacturer,
            boot_id: $boot_id,
            webview_version: $webview_version,
            webview_description: $webview_description
        },
        host: {
            loadavg: $host_load
        }
    }' >"$RUN_DIR/environment.json"

instrumentation_arguments=(
    -w
    -r
    -e class "$TEST_CLASS"
    -e e4BaseUrl "$BASE_URL"
    -e e4Token "$EVENT_TOKEN"
    -e e4EventIterations "$ITERATIONS"
)
if [[ -n "$PAPER_ID" ]]; then
    instrumentation_arguments+=(-e e4PaperId "$PAPER_ID")
fi
instrumentation_arguments+=("$TEST_PACKAGE/$TEST_RUNNER")

printf 'Running one %s event-sync instrumentation invocation with %s batch(es).\n' \
    "$MODE" "$ITERATIONS"
INSTRUMENTATION_STARTED="true"
INSTRUMENTATION_STARTED_AT_UTC="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
set +e
timeout "$INSTRUMENTATION_TIMEOUT" \
    "$ADB" -s "$SERIAL" shell am instrument \
    "${instrumentation_arguments[@]}" \
    >"$RAW_INSTRUMENTATION_LOG" 2>&1
INSTRUMENTATION_STATUS="$?"
set -e
INSTRUMENTATION_ENDED_AT_UTC="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"

if [[ "$INSTRUMENTATION_STATUS" -ne 0 ]]; then
    printf 'Instrumentation exited with status %s; partial artifacts will be preserved without retry.\n' \
        "$INSTRUMENTATION_STATUS" >&2
    exit "$INSTRUMENTATION_STATUS"
fi

redact_instrumentation_output
if ! grep -Eq '^OK \(1 test\)$' "$RUN_DIR/instrumentation_output.txt"; then
    printf 'Instrumentation did not report one passing test; artifacts will be preserved without retry.\n' >&2
    exit 1
fi
INSTRUMENTATION_REPORTED_SUCCESS="true"

printf 'Instrumentation completed; raw data and provenance will be finalized in %s\n' "$RUN_DIR"
