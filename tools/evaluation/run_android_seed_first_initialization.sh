#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
BACKEND_DIR="$REPO_ROOT/backend"
INSPECTOR="$SCRIPT_DIR/inspect_seed_first_initialization.py"
ANALYZER="$SCRIPT_DIR/analyze_seed_first_initialization.py"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
POSTGRES_ADMIN_URL="${MNEME_EVAL_POSTGRES_ADMIN_URL:-postgresql://postgres:postgres@127.0.0.1:5432/postgres}"
REDIS_PORT_BASE="${MNEME_EVAL_REDIS_PORT_BASE:-6381}"
BACKEND_PORT="${MNEME_EVAL_BACKEND_PORT:-8011}"
COOLDOWN_SECONDS="${MNEME_EVAL_INTER_TRIAL_COOLDOWN_SECONDS:-10}"
LIVE_TOKEN="${MNEME_EVAL_TOKEN:-}"
OUTPUT_ROOT="${MNEME_EVAL_OUTPUT_ROOT:-$REPO_ROOT/docs/evaluation/seed-first-initialization/raw}"
DEVICE_OUTPUT="/sdcard/Android/data/com.mneme.app/files/seed-first-initialization-evaluation"
APP_PACKAGE="com.mneme.app"
TEST_RUNNER="com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner"
TEST_CLASS="com.mneme.app.evaluation.SeedFirstInitializationMeasurementTest"
SEEDS=("1706.03762" "2010.11929" "2106.09685")

run_dir=""
work_root=""
current_stage="preflight"
current_trial_dir=""
current_private_log_dir=""
current_database=""
current_redis_url=""
current_storage=""
database_created=false
api_pid=""
worker_pid=""
redis_pid=""
status_finalized=false

record_run_status() {
    local status="$1"
    local reason="${2:-}"
    local signal_name="${3:-}"
    local exit_code="${4:-}"
    local temporary
    [[ -n "$run_dir" && -d "$run_dir" ]] || return 0
    command -v jq >/dev/null || return 0
    temporary="$run_dir/run_status.json.tmp"
    jq -n \
        --arg schema_version "seed-first-initialization-run-status-v1" \
        --arg status "$status" \
        --arg stage "$current_stage" \
        --arg reason "$reason" \
        --arg signal "$signal_name" \
        --arg exit_code "$exit_code" \
        --arg recorded_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        '{
            schema_version: $schema_version,
            status: $status,
            stage: $stage,
            reason: (if $reason == "" then null else $reason end),
            signal: (if $signal == "" then null else $signal end),
            exit_code: (if $exit_code == "" then null else ($exit_code | tonumber) end),
            recorded_at_utc: $recorded_at_utc
        }' >"$temporary"
    mv "$temporary" "$run_dir/run_status.json"
}

fail() {
    local message="$1"
    record_run_status "failed" "$message" "" "1"
    status_finalized=true
    printf 'ERROR: %s\n' "$message" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null || fail "$1 is required."
}

redact_file() {
    local source="$1"
    local destination="$2"
    [[ -f "$source" ]] || return 0
    mkdir -p "$(dirname "$destination")"
    SOURCE_FILE="$source" DESTINATION_FILE="$destination" python3 - <<'PY'
import os
from pathlib import Path

names = (
    "MNEME_EVAL_TOKEN",
    "MNEME_SEMANTIC_SCHOLAR_API_KEY",
    "MNEME_DEEPSEEK_API_KEY",
    "MNEME_OPENAI_API_KEY",
    "MNEME_ANTHROPIC_API_KEY",
)
secrets = [
    value.encode()
    for name in names
    if (value := os.environ.get(name, ""))
]
source = Path(os.environ["SOURCE_FILE"])
destination = Path(os.environ["DESTINATION_FILE"])
payload = source.read_bytes()
for secret in secrets:
    payload = payload.replace(secret, b"[REDACTED]")
destination.write_bytes(payload)
for secret in secrets:
    if secret in destination.read_bytes():
        raise SystemExit("A configured secret remained after redaction.")
PY
}

redact_retained_tree() {
    [[ -n "$run_dir" && -d "$run_dir" ]] || return 0
    RUN_DIRECTORY="$run_dir" python3 - <<'PY'
import os
from pathlib import Path

names = (
    "MNEME_EVAL_TOKEN",
    "MNEME_SEMANTIC_SCHOLAR_API_KEY",
    "MNEME_DEEPSEEK_API_KEY",
    "MNEME_OPENAI_API_KEY",
    "MNEME_ANTHROPIC_API_KEY",
)
secrets = [
    value.encode()
    for name in names
    if (value := os.environ.get(name, ""))
]
root = Path(os.environ["RUN_DIRECTORY"])
for path in root.rglob("*"):
    if not path.is_file():
        continue
    payload = path.read_bytes()
    for secret in secrets:
        payload = payload.replace(secret, b"[REDACTED]")
    path.write_bytes(payload)
for path in root.rglob("*"):
    if path.is_file() and any(secret in path.read_bytes() for secret in secrets):
        raise SystemExit(f"A configured secret remained in {path}.")
PY
}

retain_trial_logs() {
    local name
    [[ -n "$current_trial_dir" && -n "$current_private_log_dir" ]] || return 0
    for name in setup api worker redis instrumentation; do
        redact_file \
            "$current_private_log_dir/${name}_output.txt" \
            "$current_trial_dir/${name}_output.txt"
    done
}

stop_services() {
    local pid
    local attempt
    local alive
    for pid in "$api_pid" "$worker_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
        fi
    done
    for attempt in $(seq 1 20); do
        alive=false
        for pid in "$api_pid" "$worker_pid"; do
            if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
                alive=true
            fi
        done
        [[ "$alive" == false ]] && break
        sleep 0.25
    done
    for pid in "$api_pid" "$worker_pid"; do
        if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
        [[ -n "$pid" ]] && wait "$pid" 2>/dev/null || true
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
    [[ -n "$redis_pid" ]] && wait "$redis_pid" 2>/dev/null || true
    redis_pid=""
}

cleanup_trial() {
    stop_services
    stop_redis
    retain_trial_logs
    if [[ "$database_created" == true && "$current_database" =~ ^mneme_eval_si_[a-z0-9_]+$ ]]; then
        psql "$POSTGRES_ADMIN_URL" \
            -v ON_ERROR_STOP=1 \
            -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$current_database' AND pid <> pg_backend_pid();" \
            >/dev/null 2>&1 ||
            true
        dropdb --if-exists --maintenance-db="$POSTGRES_ADMIN_URL" "$current_database" \
            >/dev/null 2>&1 ||
            true
    fi
    if [[ -n "$current_storage" && -n "$work_root" && "$current_storage" == "$work_root"/mneme_eval_si_*"/storage" ]]; then
        rm -rf -- "$current_storage"
    fi
    current_trial_dir=""
    current_private_log_dir=""
    current_database=""
    current_redis_url=""
    current_storage=""
    database_created=false
}

cleanup_all() {
    set +e
    cleanup_trial
    redact_retained_tree
    if [[ -n "$work_root" && "$work_root" == /tmp/mneme_eval_seed_first.* ]]; then
        rm -rf -- "$work_root"
    fi
    if [[ -x "$ADB" ]]; then
        "$ADB" shell am force-stop "$APP_PACKAGE" >/dev/null 2>&1 || true
    fi
    set -e
}

handle_error() {
    local exit_code="$1"
    local line="$2"
    if [[ "$status_finalized" != true ]]; then
        record_run_status \
            "failed" \
            "Unexpected command failure at shell line $line." \
            "" \
            "$exit_code"
        status_finalized=true
    fi
    exit "$exit_code"
}

handle_signal() {
    local signal_name="$1"
    local exit_code="$2"
    record_run_status \
        "failed" \
        "Formal acquisition interrupted by $signal_name during $current_stage." \
        "$signal_name" \
        "$exit_code"
    status_finalized=true
    exit "$exit_code"
}

guard_local_services() {
    POSTGRES_ADMIN_URL="$POSTGRES_ADMIN_URL" python3 - <<'PY'
import os
from urllib.parse import urlparse

parsed = urlparse(os.environ["POSTGRES_ADMIN_URL"])
local_socket = parsed.hostname is None and not parsed.netloc
if (
    parsed.scheme not in {"postgresql", "postgres"}
    or (parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and not local_socket)
    or parsed.path in {"", "/"}
    or parsed.query
    or parsed.fragment
):
    raise SystemExit("PostgreSQL admin URL must name a local maintenance database.")
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

wait_for_redis() {
    local attempt
    for attempt in $(seq 1 120); do
        kill -0 "$redis_pid" 2>/dev/null ||
            fail "The dedicated Redis instance exited during startup."
        if redis-cli -u "$current_redis_url" PING 2>/dev/null | grep -q '^PONG$'; then
            return
        fi
        sleep 0.25
    done
    fail "The dedicated Redis instance was not ready within 30 seconds."
}

wait_for_backend() {
    local attempt
    for attempt in $(seq 1 120); do
        kill -0 "$api_pid" 2>/dev/null ||
            fail "The isolated API exited during startup."
        kill -0 "$worker_pid" 2>/dev/null ||
            fail "The isolated worker exited during startup."
        if curl --fail --silent "http://127.0.0.1:$BACKEND_PORT/v1/health" \
            >/dev/null &&
            grep -q 'worker_started' "$current_private_log_dir/worker_output.txt"; then
            return
        fi
        sleep 0.5
    done
    fail "The isolated API and worker were not ready within 60 seconds."
}

verify_finish_tree() {
    local allowed_prefix=""
    local path
    local -a unexpected=()
    git -C "$REPO_ROOT" diff --quiet ||
        fail "Tracked source changed during the formal run."
    git -C "$REPO_ROOT" diff --cached --quiet ||
        fail "The index changed during the formal run."
    if [[ "$run_dir" == "$REPO_ROOT"/* ]]; then
        allowed_prefix="${run_dir#"$REPO_ROOT/"}"
    fi
    while IFS= read -r -d '' path; do
        if [[ -n "$allowed_prefix" && "$path" == "$allowed_prefix"/* ]]; then
            continue
        fi
        unexpected+=("$path")
    done < <(git -C "$REPO_ROOT" ls-files --others --exclude-standard -z)
    if ((${#unexpected[@]} > 0)); then
        printf 'Unexpected untracked paths:\n' >&2
        printf '  %s\n' "${unexpected[@]}" >&2
        fail "Only the exact formal run directory may be created."
    fi
}

write_trial_status() {
    local status="$1"
    local reason="${2:-}"
    jq -n \
        --arg schema_version "seed-first-initialization-trial-status-v1" \
        --arg status "$status" \
        --arg stage "$current_stage" \
        --arg reason "$reason" \
        --arg recorded_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
        '{
            schema_version: $schema_version,
            status: $status,
            stage: $stage,
            reason: (if $reason == "" then null else $reason end),
            recorded_at_utc: $recorded_at_utc,
            measurement_invocations: 1,
            automatic_retry_performed: false
        }' >"$current_trial_dir/trial_status.json"
}

write_hash_inventory() {
    RUN_DIRECTORY="$run_dir" python3 - <<'PY'
import hashlib
import json
import os
from pathlib import Path

root = Path(os.environ["RUN_DIRECTORY"])
excluded = {"artifact_hashes.json", "run_status.json"}
entries = []
for path in sorted(item for item in root.rglob("*") if item.is_file()):
    relative = path.relative_to(root).as_posix()
    if relative in excluded:
        continue
    payload = path.read_bytes()
    entries.append(
        {
            "relative_path": relative,
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
    )
output = {
    "schema_version": "seed-first-initialization-artifact-hashes-v1",
    "excluded_mutable_files": sorted(excluded),
    "entries": entries,
}
(root / "artifact_hashes.json").write_text(
    json.dumps(output, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
}

run_self_test() {
    local temporary
    temporary="$(mktemp -d)"
    trap 'rm -rf -- "$temporary"' RETURN
    LIVE_TOKEN="self-test-token"
    export MNEME_EVAL_TOKEN="$LIVE_TOKEN"
    printf 'prefix self-test-token suffix\n' >"$temporary/source.txt"
    redact_file "$temporary/source.txt" "$temporary/redacted.txt"
    grep -q '\[REDACTED\]' "$temporary/redacted.txt"
    ! grep -q 'self-test-token' "$temporary/redacted.txt"
    [[ "$(replace_url_database 'postgresql:///postgres' 'mneme_eval_si_test')" == \
        "postgresql:///mneme_eval_si_test" ]]
    bash -n "$0"
    printf 'seed first-initialization runner self-test: PASS\n'
}

if [[ "${1:-}" == "--self-test" ]]; then
    [[ "$#" -eq 1 ]] || {
        printf 'ERROR: --self-test accepts no additional arguments.\n' >&2
        exit 2
    }
    run_self_test
    exit 0
fi
[[ "$#" -eq 0 ]] || {
    printf 'ERROR: this runner accepts only --self-test.\n' >&2
    exit 2
}

trap cleanup_all EXIT
trap 'handle_error "$?" "$LINENO"' ERR
trap 'handle_signal SIGINT 130' INT
trap 'handle_signal SIGTERM 143' TERM

[[ -x "$ADB" ]] || fail "adb was not found under $ANDROID_SDK_ROOT."
[[ -x "$JAVA_HOME/bin/javac" ]] || fail "JDK 17 was not found under $JAVA_HOME."
[[ -f "$INSPECTOR" && -f "$ANALYZER" ]] || fail "Evaluation helpers are missing."
for command in createdb curl dropdb git grep jq mv nproc psql python3 redis-cli redis-server seq sha256sum uname uv; do
    require_command "$command"
done
[[ -n "$LIVE_TOKEN" ]] ||
    fail "Set MNEME_EVAL_TOKEN; its raw value is never retained."
[[ "$REDIS_PORT_BASE" =~ ^[0-9]+$ ]] &&
    ((REDIS_PORT_BASE >= 1024 && REDIS_PORT_BASE <= 65533)) ||
    fail "Redis port base must leave three valid ports."
[[ "$BACKEND_PORT" =~ ^[0-9]+$ ]] &&
    ((BACKEND_PORT >= 1024 && BACKEND_PORT <= 65535)) ||
    fail "Backend port must be between 1024 and 65535."
[[ "$COOLDOWN_SECONDS" =~ ^[0-9]+$ ]] ||
    fail "Inter-trial cooldown must be a non-negative integer."
guard_local_services
[[ -z "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all)" ]] ||
    fail "Commit or stash all tracked and untracked changes before a formal run."
device_count="$("$ADB" devices | awk 'NR > 1 && $2 == "device" {count += 1} END {print count + 0}')"
[[ "$device_count" -eq 1 ]] ||
    fail "Exactly one ready Android device or emulator is required."
python3 - "$BACKEND_PORT" "$REDIS_PORT_BASE" <<'PY'
import socket
import sys

ports = [int(sys.argv[1]), *(int(sys.argv[2]) + offset for offset in range(3))]
if len(set(ports)) != len(ports):
    raise SystemExit("Backend and Redis ports must be distinct.")
for port in ports:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", port))
PY

run_suffix="$(python3 - <<'PY'
import secrets

print(secrets.token_hex(4))
PY
)"
run_id="mneme_eval_si_$(date -u +'%Y%m%dt%H%M%Sz')_${run_suffix}"
run_dir="$OUTPUT_ROOT/$run_id"
[[ ! -e "$run_dir" ]] || fail "The unique output directory already exists."
mkdir -p "$run_dir"
run_dir="$(cd "$run_dir" && pwd)"
work_root="$(mktemp -d "/tmp/mneme_eval_seed_first.XXXXXXXX")"
record_run_status "running"
token_sha256="$(printf '%s' "$LIVE_TOKEN" | sha256sum | awk '{print $1}')"

current_stage="android_build"
set +e
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
) >"$run_dir/build_output.txt" 2>&1
build_status=$?
set -e
[[ "$build_status" -eq 0 ]] || fail "Android build failed; output was retained."

app_apk="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
test_apk="$ANDROID_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
[[ -s "$app_apk" && -s "$test_apk" ]] || fail "Android APK outputs are missing."
"$ADB" install --no-streaming -r "$app_apk" >"$run_dir/app_install_output.txt"
"$ADB" install --no-streaming -r "$test_apk" >"$run_dir/test_install_output.txt"

declare -a USER_IDS
for _seed in "${SEEDS[@]}"; do
    USER_IDS+=("$(python3 - <<'PY'
import uuid

print(uuid.uuid4())
PY
)")
done
device_serial="$("$ADB" get-serialno | tr -d '\r')"
device_model="$("$ADB" shell getprop ro.product.model | tr -d '\r')"
device_android_release="$("$ADB" shell getprop ro.build.version.release | tr -d '\r')"
device_android_api="$("$ADB" shell getprop ro.build.version.sdk | tr -d '\r')"
device_boot_id="$("$ADB" shell cat /proc/sys/kernel/random/boot_id | tr -d '\r')"
webview_provider="$(
    "$ADB" shell dumpsys webviewupdate 2>/dev/null |
        tr -d '\r' |
        awk -F': ' '/Current WebView package/{print $2; exit}'
)"
webview_provider="${webview_provider:-not-reported}"

RUN_ID="$run_id" \
REPO_REVISION="$(git -C "$REPO_ROOT" rev-parse HEAD)" \
APP_HASH="$(sha256sum "$app_apk" | awk '{print $1}')" \
TEST_APK_HASH="$(sha256sum "$test_apk" | awk '{print $1}')" \
RUNNER_HASH="$(sha256sum "$0" | awk '{print $1}')" \
ANALYZER_HASH="$(sha256sum "$ANALYZER" | awk '{print $1}')" \
INSPECTOR_HASH="$(sha256sum "$INSPECTOR" | awk '{print $1}')" \
ANDROID_TEST_HASH="$(
    sha256sum \
        "$ANDROID_DIR/app/src/androidTest/java/com/mneme/app/evaluation/SeedFirstInitializationMeasurementTest.kt" \
        "$ANDROID_DIR/app/src/androidTest/java/com/mneme/app/evaluation/SeedFirstInitializationMeasurementFiles.kt" |
        sha256sum |
        awk '{print $1}'
)" \
USER_IDS_CSV="$(IFS=,; printf '%s' "${USER_IDS[*]}")" \
REDIS_PORT_BASE_VALUE="$REDIS_PORT_BASE" \
COOLDOWN_SECONDS_VALUE="$COOLDOWN_SECONDS" \
DEVICE_SERIAL="$device_serial" \
DEVICE_MODEL="$device_model" \
DEVICE_ANDROID_RELEASE="$device_android_release" \
DEVICE_ANDROID_API="$device_android_api" \
DEVICE_BOOT_ID="$device_boot_id" \
WEBVIEW_PROVIDER="$webview_provider" \
HOST_CPUS="$(nproc)" \
HOST_MEMORY_KIB="$(awk '/^MemTotal:/{print $2; exit}' /proc/meminfo)" \
HOST_LOAD="$(awk '{print $1 \",\" $2 \",\" $3}' /proc/loadavg)" \
HOST_KERNEL="$(uname -srmo)" \
MANIFEST_PATH="$run_dir/run_manifest.json" \
python3 - <<'PY'
import json
import os
from pathlib import Path

run_id = os.environ["RUN_ID"]
seeds = ["1706.03762", "2010.11929", "2106.09685"]
users = os.environ["USER_IDS_CSV"].split(",")
redis_base = int(os.environ["REDIS_PORT_BASE_VALUE"])
trials = []
for index, (seed, user) in enumerate(zip(seeds, users, strict=True), 1):
    trial_id = f"trial_{index:02d}"
    database = f"{run_id}_{trial_id}"
    trials.append(
        {
            "trial_id": trial_id,
            "seed_arxiv_id": seed,
            "relative_dir": f"trials/{trial_id}_{seed.replace('.', '_')}",
            "database_name": database,
            "redis_instance_port": redis_base + index - 1,
            "queue_name": f"mneme:jobs:eval:{run_id}:{trial_id}",
            "storage_namespace": database,
            "disposable_user_id": user,
            "measurement_invocations": 1,
            "automatic_retry_performed": False,
        }
    )
manifest = {
    "schema_version": "seed-first-initialization-run-manifest-v1",
    "run_id": run_id,
    "measured_at_utc": __import__("datetime").datetime.now(
        __import__("datetime").UTC
    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "repository_revision": os.environ["REPO_REVISION"],
    "fixed_seeds": seeds,
    "trials": trials,
    "timing_endpoint": (
        "Immediately before submit click to visible live five-paper briefing."
    ),
    "endpoint_semantics": (
        "Five usable papers may be ready or partial; later AI stages are outside "
        "the measured endpoint."
    ),
    "one_measurement_per_seed": True,
    "automatic_experiment_retry_enabled": False,
    "android_data_cleared_before_each_trial": True,
    "fresh_database_per_trial": True,
    "fresh_redis_per_trial": True,
    "fresh_storage_per_trial": True,
    "fresh_user_per_trial": True,
    "host_and_external_provider_state_reset": False,
    "source_tree_clean_at_start": True,
    "finish_tree_gate": "pending",
    "token_retained": False,
    "inter_trial_cooldown_seconds": int(os.environ["COOLDOWN_SECONDS_VALUE"]),
    "hashes": {
        "app_apk_sha256": os.environ["APP_HASH"],
        "test_apk_sha256": os.environ["TEST_APK_HASH"],
        "runner_sha256": os.environ["RUNNER_HASH"],
        "analyzer_sha256": os.environ["ANALYZER_HASH"],
        "inspector_sha256": os.environ["INSPECTOR_HASH"],
        "android_test_sources_sha256": os.environ["ANDROID_TEST_HASH"],
    },
    "device_environment": {
        "serial": os.environ["DEVICE_SERIAL"],
        "model": os.environ["DEVICE_MODEL"],
        "android_release": os.environ["DEVICE_ANDROID_RELEASE"],
        "android_api": os.environ["DEVICE_ANDROID_API"],
        "boot_id": os.environ["DEVICE_BOOT_ID"],
        "webview_provider": os.environ["WEBVIEW_PROVIDER"],
    },
    "host_environment": {
        "logical_cpus": os.environ["HOST_CPUS"],
        "memory_kib": os.environ["HOST_MEMORY_KIB"],
        "load_average_1m_5m_15m": os.environ["HOST_LOAD"],
        "kernel": os.environ["HOST_KERNEL"],
    },
}
Path(os.environ["MANIFEST_PATH"]).write_text(
    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY

failed_trials=0
for index in "${!SEEDS[@]}"; do
    number=$((index + 1))
    trial_id="$(printf 'trial_%02d' "$number")"
    seed="${SEEDS[$index]}"
    seed_slug="${seed//./_}"
    current_trial_dir="$run_dir/trials/${trial_id}_${seed_slug}"
    current_database="${run_id}_${trial_id}"
    redis_port=$((REDIS_PORT_BASE + index))
    current_redis_url="redis://127.0.0.1:${redis_port}/0"
    current_storage="$work_root/$current_database/storage"
    redis_dir="$work_root/$current_database/redis"
    current_private_log_dir="$work_root/$current_database/logs"
    queue_name="mneme:jobs:eval:${run_id}:${trial_id}"
    user_id="${USER_IDS[$index]}"
    database_url="$(replace_url_database "$POSTGRES_ADMIN_URL" "$current_database")"

    current_stage="${trial_id}_isolated_state_setup"
    mkdir -p "$current_storage" "$redis_dir" "$current_private_log_dir" "$current_trial_dir"
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
    wait_for_redis

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
    (
        cd "$BACKEND_DIR"
        uv run python "$INSPECTOR" precondition \
            --output "$current_trial_dir/precondition.json" \
            --trial-id "$trial_id" \
            --seed "$seed"
    ) >"$current_trial_dir/precondition_output.txt" 2>&1

    current_stage="${trial_id}_backend_start"
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
    wait_for_backend

    current_stage="${trial_id}_android_measurement"
    [[ ! -e "$current_trial_dir/measurement_attempt.json" ]] ||
        fail "$trial_id already has a measurement attempt marker."
    jq -n \
        --arg trial_id "$trial_id" \
        --arg seed "$seed" \
        '{
            schema_version: "seed-first-initialization-attempt-v1",
            trial_id: $trial_id,
            seed_arxiv_id: $seed,
            invocation: 1,
            automatic_retry: false
        }' >"$current_trial_dir/measurement_attempt.json"
    "$ADB" shell pm clear --user 0 "$APP_PACKAGE" \
        >"$current_trial_dir/android_data_clear_output.txt" 2>&1 ||
        fail "Could not clear Android data before $trial_id."
    "$ADB" shell rm -rf "$DEVICE_OUTPUT" >/dev/null 2>&1 || true
    set +e
    "$ADB" shell am instrument \
        -w \
        -r \
        --no-window-animation \
        --user 0 \
        -e class "$TEST_CLASS" \
        -e seedFirstTrial "$trial_id" \
        -e seedFirstSeed "$seed" \
        -e seedFirstBaseUrl "http://10.0.2.2:$BACKEND_PORT/v1/" \
        -e seedFirstToken "$LIVE_TOKEN" \
        "$TEST_RUNNER" >"$current_private_log_dir/instrumentation_output.txt" 2>&1
    instrumentation_status=$?
    set -e
    instrumentation_reported_success=false
    if [[ "$instrumentation_status" -eq 0 ]] &&
        grep -q '^OK (1 test)' "$current_private_log_dir/instrumentation_output.txt"; then
        instrumentation_reported_success=true
    fi
    set +e
    "$ADB" pull "$DEVICE_OUTPUT/measurement.csv" \
        "$current_trial_dir/android_measurement.csv" \
        >"$current_trial_dir/android_pull_output.txt" 2>&1
    pull_status=$?
    set -e

    current_stage="${trial_id}_backend_snapshot"
    snapshot_status=1
    if [[ "$pull_status" -eq 0 && -s "$current_trial_dir/android_measurement.csv" ]]; then
        set +e
        (
            cd "$BACKEND_DIR"
            uv run python "$INSPECTOR" post \
                --output "$current_trial_dir/backend_snapshot.json" \
                --trial-id "$trial_id" \
                --seed "$seed" \
                --measurement "$current_trial_dir/android_measurement.csv"
        ) >"$current_trial_dir/backend_snapshot_output.txt" 2>&1
        snapshot_status=$?
        set -e
    fi

    stop_services
    stop_redis
    retain_trial_logs
    redact_retained_tree
    current_stage="${trial_id}_immediate_validation"
    validation_status=1
    if [[
        "$instrumentation_status" -eq 0 &&
        "$instrumentation_reported_success" == true &&
        "$pull_status" -eq 0 &&
        "$snapshot_status" -eq 0
    ]]; then
        set +e
        python3 "$ANALYZER" validate-trial \
            --run-dir "$run_dir" \
            --trial-id "$trial_id" \
            >"$current_trial_dir/immediate_validation_output.txt" 2>&1
        validation_status=$?
        set -e
    else
        jq -n \
            --arg instrumentation_status "$instrumentation_status" \
            --arg instrumentation_reported_success "$instrumentation_reported_success" \
            --arg pull_status "$pull_status" \
            --arg snapshot_status "$snapshot_status" \
            '{
                schema_version: "seed-first-initialization-trial-validation-v1",
                passed: false,
                error_type: "TrialExecutionFailure",
                error: (
                    "instrumentation=" + $instrumentation_status
                    + ", instrumentation_reported_success="
                    + $instrumentation_reported_success
                    + ", pull=" + $pull_status
                    + ", snapshot=" + $snapshot_status
                )
            }' >"$current_trial_dir/immediate_validation.json"
    fi
    if [[ "$validation_status" -eq 0 ]]; then
        write_trial_status "passed"
    else
        write_trial_status "failed" \
            "The one permitted measurement did not pass immediate validation."
        failed_trials=$((failed_trials + 1))
    fi
    current_stage="${trial_id}_cleanup"
    cleanup_trial
    if ((index + 1 < ${#SEEDS[@]} && COOLDOWN_SECONDS > 0)); then
        current_stage="${trial_id}_fixed_cooldown"
        sleep "$COOLDOWN_SECONDS"
    fi
done

current_stage="finish_tree_check"
redact_retained_tree
verify_finish_tree
temporary_manifest="$run_dir/run_manifest.json.tmp"
jq '.finish_tree_gate = "passed"' "$run_dir/run_manifest.json" >"$temporary_manifest"
mv "$temporary_manifest" "$run_dir/run_manifest.json"

if ((failed_trials > 0)); then
    current_stage="incomplete"
    write_hash_inventory
    record_run_status \
        "failed" \
        "$failed_trials of three fixed one-shot trials failed; no formal summary was produced." \
        "" \
        "1"
    status_finalized=true
    trap - ERR
    exit 1
fi

current_stage="analysis"
python3 "$ANALYZER" analyze --run-dir "$run_dir" \
    >"$run_dir/analysis_output.txt" 2>&1
current_stage="complete"
jq -n \
    --arg schema_version "seed-first-initialization-completed-v1" \
    --arg completed_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    '{
        schema_version: $schema_version,
        completed_at_utc: $completed_at_utc,
        fixed_trials_completed: 3,
        automatic_retries: 0
    }' >"$run_dir/experiment_completed.json"
redact_retained_tree
write_hash_inventory
verify_finish_tree
record_run_status "passed" "" "" "0"
status_finalized=true
trap - ERR
trap - INT
trap - TERM
trap - EXIT
cleanup_all
printf 'Seed first-initialization evidence and analysis written to %s\n' "$run_dir"
