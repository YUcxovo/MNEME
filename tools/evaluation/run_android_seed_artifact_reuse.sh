#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
BACKEND_DIR="$REPO_ROOT/backend"
INSPECTOR="$SCRIPT_DIR/inspect_seed_artifact_state.py"
ANALYZER="$SCRIPT_DIR/analyze_seed_artifact_reuse.py"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
POSTGRES_ADMIN_URL="${MNEME_EVAL_POSTGRES_ADMIN_URL:-postgresql://postgres:postgres@127.0.0.1:5432/postgres}"
REDIS_PORT_BASE="${MNEME_EVAL_REDIS_PORT_BASE:-6381}"
BACKEND_PORT="${MNEME_EVAL_BACKEND_PORT:-8011}"
LIVE_TOKEN="${MNEME_EVAL_TOKEN:-}"
OUTPUT_ROOT="${MNEME_EVAL_OUTPUT_ROOT:-$REPO_ROOT/docs/evaluation/seed-artifact-reuse/raw}"
DEVICE_OUTPUT="/sdcard/Android/data/com.mneme.app/files/seed-artifact-reuse-evaluation"
APP_PACKAGE="com.mneme.app"
TEST_RUNNER="com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner"
TEST_CLASS="com.mneme.app.evaluation.SeedArtifactReuseMeasurementTest"
SEEDS=("1706.03762" "2010.11929" "2106.09685")
run_dir=""
current_stage="preflight"
current_pair_dir=""
current_private_log_dir=""

fail() {
    record_run_status "failed"
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null || fail "$1 is required."
}

record_run_status() {
    local status="$1"
    local temporary
    if [[ -z "$run_dir" || ! -d "$run_dir" ]] || ! command -v jq >/dev/null; then
        return
    fi
    temporary="$run_dir/run_status.json.tmp"
    jq -n \
        --arg schema_version "seed-artifact-reuse-run-status-v1" \
        --arg status "$status" \
        --arg stage "$current_stage" \
        --arg recorded_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        '{
            schema_version: $schema_version,
            status: $status,
            stage: $stage,
            recorded_at_utc: $recorded_at_utc
        }' >"$temporary"
    mv "$temporary" "$run_dir/run_status.json"
}

redact_file() {
    local source="$1"
    local destination="$2"
    [[ -f "$source" ]] || return
    mkdir -p "$(dirname "$destination")"
    TOKEN_VALUE="$LIVE_TOKEN" python3 - "$source" "$destination" <<'PY'
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
token = os.environ["TOKEN_VALUE"].encode()
payload = source.read_bytes()
if token:
    payload = payload.replace(token, b"[REDACTED]")
destination.write_bytes(payload)
if token and token in destination.read_bytes():
    raise SystemExit("Raw evaluation token remained after redaction.")
PY
}

retain_pair_logs() {
    local name
    [[ -n "$current_pair_dir" && -n "$current_private_log_dir" ]] || return
    for name in setup api worker redis; do
        redact_file \
            "$current_private_log_dir/${name}_output.txt" \
            "$current_pair_dir/${name}_output.txt"
    done
}

redact_retained_tree() {
    [[ -n "$run_dir" && -d "$run_dir" ]] || return
    TOKEN_VALUE="$LIVE_TOKEN" RUN_DIRECTORY="$run_dir" python3 - <<'PY'
import os
from pathlib import Path

token = os.environ["TOKEN_VALUE"].encode()
root = Path(os.environ["RUN_DIRECTORY"])
if token:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        payload = path.read_bytes()
        if token in payload:
            path.write_bytes(payload.replace(token, b"[REDACTED]"))
    if any(token in path.read_bytes() for path in root.rglob("*") if path.is_file()):
        raise SystemExit("Raw evaluation token remained in retained artifacts.")
PY
}

guard_local_services() {
    POSTGRES_ADMIN_URL="$POSTGRES_ADMIN_URL" python3 - <<'PY'
import os
from urllib.parse import urlparse

local_hosts = {"localhost", "127.0.0.1", "::1"}
postgres = urlparse(os.environ["POSTGRES_ADMIN_URL"])
local_unix_socket = postgres.hostname is None and not postgres.netloc
if (
    postgres.scheme not in {"postgresql", "postgres"}
    or (postgres.hostname not in local_hosts and not local_unix_socket)
):
    raise SystemExit("PostgreSQL admin URL must target a local PostgreSQL server.")
if postgres.path in {"", "/"}:
    raise SystemExit("PostgreSQL admin URL must name a maintenance database.")
if postgres.query or postgres.fragment:
    raise SystemExit("PostgreSQL admin URL must not contain a query or fragment.")
PY
}

replace_url_database() {
    local url="$1"
    local database_name="$2"
    URL_VALUE="$url" DATABASE_NAME="$database_name" python3 - <<'PY'
import os
from urllib.parse import urlsplit, urlunsplit

parts = urlsplit(os.environ["URL_VALUE"])
database = os.environ["DATABASE_NAME"]
if parts.netloc:
    print(urlunsplit((parts.scheme, parts.netloc, "/" + database, "", "")))
else:
    print(f"{parts.scheme}:///{database}")
PY
}

api_pid=""
worker_pid=""
redis_pid=""
current_database=""
current_redis_url=""
current_storage=""
database_created=false
work_root=""

stop_services() {
    local pid
    local attempt
    local services_alive
    for pid in "$api_pid" "$worker_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    for attempt in $(seq 1 20); do
        services_alive=false
        for pid in "$api_pid" "$worker_pid"; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                services_alive=true
            fi
        done
        [[ "$services_alive" == false ]] && break
        sleep 0.25
    done
    for pid in "$api_pid" "$worker_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
    for pid in "$api_pid" "$worker_pid"; do
        if [[ -n "$pid" ]]; then
            wait "$pid" 2>/dev/null || true
        fi
    done
    api_pid=""
    worker_pid=""
}

stop_redis() {
    local attempt
    if [[ -n "$redis_pid" ]] && kill -0 "$redis_pid" 2>/dev/null; then
        kill "$redis_pid" 2>/dev/null || true
        for attempt in $(seq 1 20); do
            kill -0 "$redis_pid" 2>/dev/null || break
            sleep 0.25
        done
        if kill -0 "$redis_pid" 2>/dev/null; then
            kill -KILL "$redis_pid" 2>/dev/null || true
        fi
    fi
    if [[ -n "$redis_pid" ]]; then
        wait "$redis_pid" 2>/dev/null || true
    fi
    redis_pid=""
}

cleanup_pair() {
    stop_services
    stop_redis
    retain_pair_logs
    if [[ "$database_created" == true ]]; then
        [[ "$current_database" =~ ^mneme_eval_[a-z0-9_]+$ ]] ||
            fail "Refusing to drop an unguarded database name."
        psql "$POSTGRES_ADMIN_URL" \
            -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$current_database' AND pid <> pg_backend_pid();" \
            >/dev/null 2>&1 ||
            true
        dropdb --if-exists --maintenance-db="$POSTGRES_ADMIN_URL" "$current_database" \
            >/dev/null 2>&1 ||
            true
    fi
    if [[ -n "$current_storage" ]]; then
        [[ "$current_storage" == "$work_root"/mneme_eval_*"/storage" ]] ||
            fail "Refusing to remove an unguarded storage path."
        rm -rf -- "$current_storage"
    fi
    current_database=""
    current_redis_url=""
    current_storage=""
    current_pair_dir=""
    current_private_log_dir=""
    database_created=false
}

cleanup_all() {
    cleanup_pair
    redact_retained_tree
    if [[ -n "$work_root" && "$work_root" == /tmp/mneme_eval_seed_reuse.* ]]; then
        rm -rf -- "$work_root"
    fi
    "$ADB" shell am force-stop "$APP_PACKAGE" >/dev/null 2>&1 || true
}

pull_android_measurement() {
    local destination="$1"
    mkdir -p "$destination"
    "$ADB" pull "$DEVICE_OUTPUT/measurement.csv" \
        "$destination/android_measurement.csv" >/dev/null 2>&1 ||
        true
}

run_android_condition() {
    local pair_id="$1"
    local seed="$2"
    local condition="$3"
    local destination="$4"
    local base_url="http://10.0.2.2:$BACKEND_PORT/v1/"
    local instrumentation_status
    local private_output="$current_private_log_dir/instrumentation_${condition}_output.txt"

    mkdir -p "$destination"
    "$ADB" shell pm clear --user 0 "$APP_PACKAGE" >/dev/null ||
        fail "Could not clear Android application data before $pair_id/$condition."
    "$ADB" shell rm -rf "$DEVICE_OUTPUT" >/dev/null 2>&1 || true

    set +e
    "$ADB" shell am instrument \
        -w \
        -r \
        --no-window-animation \
        --user 0 \
        -e class "$TEST_CLASS" \
        -e seedReusePair "$pair_id" \
        -e seedReuseSeed "$seed" \
        -e seedReuseCondition "$condition" \
        -e seedReuseBaseUrl "$base_url" \
        -e seedReuseToken "$LIVE_TOKEN" \
        "$TEST_RUNNER" >"$private_output" 2>&1
    instrumentation_status=$?
    set -e
    redact_file "$private_output" "$destination/instrumentation_output.txt"
    while IFS= read -r line; do
        printf '%s\n' "$line"
    done <"$destination/instrumentation_output.txt"

    pull_android_measurement "$destination"
    [[ -s "$destination/android_measurement.csv" ]] ||
        fail "$pair_id/$condition produced no raw Android measurement; no retry was attempted."
    [[ "$instrumentation_status" -eq 0 ]] ||
        fail "$pair_id/$condition instrumentation failed; raw evidence was retained."
    grep -q '^OK (1 test)' "$destination/instrumentation_output.txt" ||
        fail "$pair_id/$condition did not report one passing test; no retry was attempted."
}

wait_for_backend() {
    local api_log="$1"
    local worker_log="$2"
    local attempt
    for attempt in $(seq 1 120); do
        kill -0 "$api_pid" 2>/dev/null ||
            fail "The isolated backend exited during startup; see $api_log."
        kill -0 "$worker_pid" 2>/dev/null ||
            fail "The isolated worker exited during startup; see $worker_log."
        if curl --fail --silent "http://127.0.0.1:$BACKEND_PORT/v1/health" \
            >/dev/null &&
            grep -q 'worker_started' "$worker_log"; then
            return
        fi
        sleep 0.5
    done
    fail "The isolated backend and worker were not ready within 60 seconds."
}

wait_for_redis() {
    local redis_log="$1"
    local attempt
    for attempt in $(seq 1 120); do
        kill -0 "$redis_pid" 2>/dev/null ||
            fail "The dedicated Redis instance exited during startup; see $redis_log."
        if redis-cli -u "$current_redis_url" PING 2>/dev/null | grep -q '^PONG$'; then
            return
        fi
        sleep 0.25
    done
    fail "The dedicated Redis instance was not ready within 30 seconds."
}

verify_finish_tree() {
    local allowed_prefix=""
    local path
    local -a unexpected_untracked=()

    git -C "$REPO_ROOT" diff --quiet ||
        fail "Tracked source changed during the formal run; raw evidence was retained."
    git -C "$REPO_ROOT" diff --cached --quiet ||
        fail "The index changed during the formal run; raw evidence was retained."
    if [[ "$run_dir" == "$REPO_ROOT"/* ]]; then
        allowed_prefix="${run_dir#"$REPO_ROOT/"}"
    fi
    while IFS= read -r -d '' path; do
        if [[ -n "$allowed_prefix" && "$path" == "$allowed_prefix"/* ]]; then
            continue
        fi
        unexpected_untracked+=("$path")
    done < <(git -C "$REPO_ROOT" ls-files --others --exclude-standard -z)
    if ((${#unexpected_untracked[@]} > 0)); then
        printf 'Unexpected untracked paths created during the run:\n' >&2
        printf '  %s\n' "${unexpected_untracked[@]}" >&2
        fail "Only files under the exact formal run directory may be created."
    fi
}

[[ -x "$ADB" ]] || fail "adb was not found under $ANDROID_SDK_ROOT."
[[ -x "$JAVA_HOME/bin/javac" ]] || fail "JDK 17 was not found under $JAVA_HOME."
[[ -f "$INSPECTOR" && -f "$ANALYZER" ]] || fail "Evaluation helper scripts are missing."
for command in awk createdb curl dirname dropdb git jq mv nproc psql python3 redis-cli redis-server seq sha256sum tr uname uv; do
    require_command "$command"
done
[[ -n "$LIVE_TOKEN" ]] ||
    fail "Set MNEME_EVAL_TOKEN; the raw token is passed to Android and never retained."
[[ "$REDIS_PORT_BASE" =~ ^[0-9]+$ ]] &&
    ((REDIS_PORT_BASE >= 1024 && REDIS_PORT_BASE <= 65533)) ||
    fail "Redis port base must leave three ports between 1024 and 65535."
[[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] &&
    ((BACKEND_PORT >= 1024 && BACKEND_PORT <= 65535)) ||
    fail "Backend port must be between 1024 and 65535."
guard_local_services

[[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]] ||
    fail "Commit or stash all tracked and untracked changes before a formal run."
device_count="$("$ADB" devices | awk 'NR > 1 && $2 == "device" { count += 1 } END { print count + 0 }')"
[[ "$device_count" -eq 1 ]] || fail "Exactly one ready Android device or emulator is required."

python3 - "$BACKEND_PORT" "$REDIS_PORT_BASE" <<'PY'
import socket
import sys

ports = [int(sys.argv[1]), *(int(sys.argv[2]) + offset for offset in range(3))]
if len(set(ports)) != len(ports):
    raise SystemExit("Backend and dedicated Redis ports must be distinct.")
for port in ports:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", port))
PY

run_suffix="$(python3 - <<'PY'
import secrets

print(secrets.token_hex(4))
PY
)"
run_id="mneme_eval_sr_$(date -u +'%Y%m%dt%H%M%Sz')_${run_suffix}"
run_dir="$OUTPUT_ROOT/$run_id"
[[ ! -e "$run_dir" ]] || fail "The unique output directory already exists."
mkdir -p "$run_dir"
run_dir="$(cd "$run_dir" && pwd)"
work_root="$(mktemp -d "/tmp/mneme_eval_seed_reuse.XXXXXXXX")"
trap cleanup_all EXIT
trap 'record_run_status "failed"' ERR
token_sha256="$(printf '%s' "$LIVE_TOKEN" | sha256sum | awk '{print $1}')"

current_stage="android_build"
(
    cd "$ANDROID_DIR"
    ANDROID_HOME="$ANDROID_SDK_ROOT" \
        ANDROID_SDK_ROOT="$ANDROID_SDK_ROOT" \
        JAVA_HOME="$JAVA_HOME" \
        MNEME_DEMO_TOKEN="" \
        ./gradlew \
        ktlintCheck \
        detekt \
        lintDebug \
        testDebugUnitTest \
        assembleDebug \
        assembleDebugAndroidTest
)

app_apk="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
test_apk="$ANDROID_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
[[ -s "$app_apk" && -s "$test_apk" ]] || fail "Android APK outputs are missing."
app_apk_sha256="$(sha256sum "$app_apk" | awk '{print $1}')"
test_apk_sha256="$(sha256sum "$test_apk" | awk '{print $1}')"

"$ADB" install --no-streaming -r "$app_apk" >/dev/null
"$ADB" install --no-streaming -r "$test_apk" >/dev/null

device_serial="$("$ADB" get-serialno | tr -d '\r')"
device_model="$("$ADB" shell getprop ro.product.model | tr -d '\r')"
device_product="$("$ADB" shell getprop ro.product.name | tr -d '\r')"
device_android_release="$("$ADB" shell getprop ro.build.version.release | tr -d '\r')"
device_android_api="$("$ADB" shell getprop ro.build.version.sdk | tr -d '\r')"
device_boot_id="$("$ADB" shell cat /proc/sys/kernel/random/boot_id | tr -d '\r')"
webview_provider="$(
    "$ADB" shell dumpsys webviewupdate 2>/dev/null |
        tr -d '\r' |
        awk -F': ' '/Current WebView package/{print $2; exit}'
)"
webview_provider="${webview_provider:-not-reported}"
host_logical_cpus="$(nproc)"
host_memory_kib="$(awk '/^MemTotal:/{print $2; exit}' /proc/meminfo)"
host_load_average="$(awk '{print $1\",\"$2\",\"$3}' /proc/loadavg)"
host_kernel="$(uname -srmo)"

jq -n \
    --arg schema_version "seed-artifact-reuse-run-manifest-v1" \
    --arg run_id "$run_id" \
    --arg measured_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg repository_revision "$(git -C "$REPO_ROOT" rev-parse HEAD)" \
    --arg app_apk_sha256 "$app_apk_sha256" \
    --arg test_apk_sha256 "$test_apk_sha256" \
    --arg runner_sha256 "$(sha256sum "$0" | awk '{print $1}')" \
    --arg inspector_sha256 "$(sha256sum "$INSPECTOR" | awk '{print $1}')" \
    --arg analyzer_sha256 "$(sha256sum "$ANALYZER" | awk '{print $1}')" \
    --arg test_sources_sha256 "$(
        sha256sum \
            "$ANDROID_DIR/app/src/androidTest/java/com/mneme/app/evaluation/SeedArtifactReuseMeasurementTest.kt" \
            "$ANDROID_DIR/app/src/androidTest/java/com/mneme/app/evaluation/SeedArtifactReuseMeasurementFiles.kt" |
            sha256sum |
            awk '{print $1}'
    )" \
    --arg device_serial "$device_serial" \
    --arg device_model "$device_model" \
    --arg device_product "$device_product" \
    --arg device_android_release "$device_android_release" \
    --arg device_android_api "$device_android_api" \
    --arg device_boot_id "$device_boot_id" \
    --arg webview_provider "$webview_provider" \
    --arg host_logical_cpus "$host_logical_cpus" \
    --arg host_memory_kib "$host_memory_kib" \
    --arg host_load_average "$host_load_average" \
    --arg host_kernel "$host_kernel" \
    --argjson redis_port_base "$REDIS_PORT_BASE" \
    '{
        schema_version: $schema_version,
        run_id: $run_id,
        measured_at_utc: $measured_at_utc,
        repository_revision: $repository_revision,
        fixed_seeds: ["1706.03762", "2010.11929", "2106.09685"],
        pairs: [
            {
                pair_id: "pair_01",
                seed_arxiv_id: "1706.03762",
                relative_dir: "pairs/pair_01_1706_03762",
                database_name: ($run_id + "_pair_01"),
                queue_name: ("mneme:jobs:eval:" + $run_id + ":pair_01"),
                redis_database: 0,
                redis_instance_port: $redis_port_base
            },
            {
                pair_id: "pair_02",
                seed_arxiv_id: "2010.11929",
                relative_dir: "pairs/pair_02_2010_11929",
                database_name: ($run_id + "_pair_02"),
                queue_name: ("mneme:jobs:eval:" + $run_id + ":pair_02"),
                redis_database: 0,
                redis_instance_port: ($redis_port_base + 1)
            },
            {
                pair_id: "pair_03",
                seed_arxiv_id: "2106.09685",
                relative_dir: "pairs/pair_03_2106_09685",
                database_name: ($run_id + "_pair_03"),
                queue_name: ("mneme:jobs:eval:" + $run_id + ":pair_03"),
                redis_database: 0,
                redis_instance_port: ($redis_port_base + 2)
            }
        ],
        timing_endpoint: "Immediately before submit click to visible live five-paper briefing.",
        source_tree_clean_at_start: true,
        finish_tree_gate: "pending",
        android_data_cleared_before_each_condition: true,
        backend_state_preserved_between_first_and_reuse: true,
        dedicated_redis_instance_per_pair: true,
        failed_runs_retried: false,
        token_retained: false,
        hashes: {
            app_apk_sha256: $app_apk_sha256,
            test_apk_sha256: $test_apk_sha256,
            runner_sha256: $runner_sha256,
            inspector_sha256: $inspector_sha256,
            analyzer_sha256: $analyzer_sha256,
            android_test_sources_sha256: $test_sources_sha256
        },
        device_environment: {
            serial: $device_serial,
            model: $device_model,
            product: $device_product,
            android_release: $device_android_release,
            android_api: $device_android_api,
            boot_id: $device_boot_id,
            webview_provider: $webview_provider
        },
        host_environment: {
            logical_cpus: $host_logical_cpus,
            memory_kib: $host_memory_kib,
            load_average_1m_5m_15m: $host_load_average,
            kernel: $host_kernel
        },
        interpretation: "Seed-to-visible-briefing latency under paired reuse-eligible backend state. Immutable jobs and artifacts are verified, but the contrast is not a causal isolation of artifact caching.",
        analysis: "Three fixed paired observations; descriptive median and range only."
    }' >"$run_dir/run_manifest.json"

for index in "${!SEEDS[@]}"; do
    pair_number=$((index + 1))
    pair_id="$(printf 'pair_%02d' "$pair_number")"
    seed="${SEEDS[$index]}"
    seed_slug="${seed//./_}"
    pair_dir="$run_dir/pairs/${pair_id}_${seed_slug}"
    current_pair_dir="$pair_dir"
    current_database="${run_id}_${pair_id}"
    redis_port=$((REDIS_PORT_BASE + index))
    current_redis_url="redis://127.0.0.1:${redis_port}/0"
    current_storage="$work_root/$current_database/storage"
    redis_dir="$work_root/$current_database/redis"
    current_private_log_dir="$work_root/$current_database/logs"
    queue_name="mneme:jobs:eval:${run_id}:${pair_id}"
    user_id="$(python3 - <<'PY'
import uuid

print(uuid.uuid4())
PY
)"
    database_url="$(replace_url_database "$POSTGRES_ADMIN_URL" "$current_database")"

    [[ "$current_database" =~ ^mneme_eval_[a-z0-9_]+$ ]] ||
        fail "Generated database name did not pass the disposal guard."
    current_stage="${pair_id}_isolated_state_setup"
    mkdir -p "$current_storage" "$redis_dir" "$current_private_log_dir" "$pair_dir"
    createdb --maintenance-db="$POSTGRES_ADMIN_URL" "$current_database"
    database_created=true
    redis-server \
        --bind 127.0.0.1 \
        --protected-mode yes \
        --port "$redis_port" \
        --dir "$redis_dir" \
        --save "" \
        --appendonly no \
        --daemonize no \
        >"$current_private_log_dir/redis_output.txt" 2>&1 &
    redis_pid=$!
    wait_for_redis "$current_private_log_dir/redis_output.txt"

    export MNEME_DATABASE_URL="$database_url"
    export MNEME_REDIS_URL="$current_redis_url"
    export MNEME_ARQ_QUEUE_NAME="$queue_name"
    export MNEME_PAPER_STORAGE_DIR="$current_storage"
    export MNEME_DEMO_USER_ID="$user_id"
    export MNEME_DEMO_TOKEN_SHA256="$token_sha256"
    export MNEME_ENVIRONMENT="testing"
    export MNEME_DEBUG="false"
    export MNEME_EVAL_RUN_ID="$run_id"
    export MNEME_EVAL_REDIS_INSTANCE_PORT="$redis_port"

    (
        cd "$BACKEND_DIR"
        uv run alembic upgrade head
        uv run python -m mneme.cli.bootstrap_demo_user
    ) >"$current_private_log_dir/setup_output.txt" 2>&1

    current_stage="${pair_id}_backend_start"
    (
        cd "$BACKEND_DIR"
        exec uv run arq mneme.tasks.worker.WorkerSettings
    ) >"$current_private_log_dir/worker_output.txt" 2>&1 &
    worker_pid=$!
    (
        cd "$BACKEND_DIR"
        exec uv run uvicorn mneme.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
    ) >"$current_private_log_dir/api_output.txt" 2>&1 &
    api_pid=$!
    wait_for_backend \
        "$current_private_log_dir/api_output.txt" \
        "$current_private_log_dir/worker_output.txt"

    current_stage="${pair_id}_first"
    run_android_condition "$pair_id" "$seed" "first" "$pair_dir/first"
    current_stage="${pair_id}_after_first_snapshot"
    (
        cd "$BACKEND_DIR"
        uv run python "$INSPECTOR" \
            --output "$pair_dir/after_first_backend.json" \
            --pair-id "$pair_id" \
            --seed "$seed" \
            --phase after_first
    ) >"$pair_dir/after_first_inspector_output.txt" 2>&1

    current_stage="${pair_id}_reuse"
    run_android_condition "$pair_id" "$seed" "reuse" "$pair_dir/reuse"
    current_stage="${pair_id}_after_reuse_snapshot"
    (
        cd "$BACKEND_DIR"
        uv run python "$INSPECTOR" \
            --output "$pair_dir/after_reuse_backend.json" \
            --pair-id "$pair_id" \
            --seed "$seed" \
            --phase after_reuse
    ) >"$pair_dir/after_reuse_inspector_output.txt" 2>&1

    current_stage="${pair_id}_cleanup"
    cleanup_pair
done

current_stage="pre_analysis_tree_check"
redact_retained_tree
verify_finish_tree
temporary_manifest="$run_dir/run_manifest.json.tmp"
jq '.finish_tree_gate = "passed"' "$run_dir/run_manifest.json" >"$temporary_manifest"
mv "$temporary_manifest" "$run_dir/run_manifest.json"
current_stage="analysis"
python3 "$ANALYZER" --run-dir "$run_dir" >"$run_dir/analysis_output.txt" 2>&1
current_stage="finish_tree_check"
verify_finish_tree
current_stage="complete"
record_run_status "passed"
redact_retained_tree
verify_finish_tree
trap - ERR
trap - EXIT
cleanup_all
printf 'Seed artifact-reuse raw evidence and analysis written to %s\n' "$run_dir"
