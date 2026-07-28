#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
EVALUATION_DIR="$REPO_ROOT/docs/evaluation/android-formal"
RAW_ROOT="${MNEME_FORMAL_RAW_ROOT:-$EVALUATION_DIR/raw}"
ANALYZER="$SCRIPT_DIR/analyze_android_formal_resource_matrix.py"

ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
EMULATOR="$ANDROID_SDK_ROOT/emulator/emulator"
AVD_NAME="${MNEME_FORMAL_AVD:-Mneme_Factorial_API_34_Pixel6}"
HOST_CPUSET="${MNEME_FORMAL_HOST_CPUSET:-4-11}"
BOOT_TIMEOUT_SECONDS="${MNEME_FORMAL_BOOT_TIMEOUT_SECONDS:-240}"
BOOT_STABILIZATION_SECONDS="${MNEME_FORMAL_BOOT_STABILIZATION_SECONDS:-10}"
SESSION_TIMEOUT="${MNEME_FORMAL_SESSION_TIMEOUT:-8m}"
STARTUP_TIMEOUT="${MNEME_FORMAL_STARTUP_TIMEOUT:-6m}"
GRAPH_TIMEOUT="${MNEME_FORMAL_GRAPH_TIMEOUT:-4m}"

STARTUP_CONNECTED_TASK=":benchmark:connectedBenchmarkAndroidTest"
STARTUP_TEST_CLASS="com.mneme.app.benchmark.MnemeStartupBenchmark"
STARTUP_OUTPUT_ROOT="$ANDROID_DIR/benchmark/build/outputs/connected_android_test_additional_output/benchmark/connected"
STARTUP_APP_APK_SOURCE="$ANDROID_DIR/app/build/outputs/apk/benchmark/app-benchmark.apk"
STARTUP_BENCHMARK_APK_SOURCE="$ANDROID_DIR/benchmark/build/outputs/apk/benchmark/benchmark-benchmark.apk"
STARTUP_COLD_METRIC="timeToFullDisplayMs"
STARTUP_RESUME_METRIC="timeToInitialDisplayMs"

GRAPH_APP_APK_SOURCE="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
GRAPH_TEST_APK_SOURCE="$ANDROID_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
GRAPH_TEST_CLASS="com.mneme.app.ui.graph.E4GraphMeasurementTest#recordBoundedRendererLatency"
GRAPH_TEST_RUNNER="com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner"
DEVICE_EVALUATION_DIR="/sdcard/Android/data/com.mneme.app/files/e4-evaluation"
CONTROLLED_UNREACHABLE_BASE_URL="http://127.0.0.1:9/v1/"

BUILD_TASKS=(
    ktlintCheck
    detekt
    lintDebug
    testDebugUnitTest
    :app:assembleDebug
    :app:assembleDebugAndroidTest
    :app:assembleBenchmark
    :benchmark:assembleBenchmark
)

BLOCK_ORDERS=(
    "cpu2_ram2gb cpu2_ram6gb cpu4_ram6gb cpu4_ram2gb"
    "cpu4_ram2gb cpu4_ram6gb cpu2_ram6gb cpu2_ram2gb"
)
NODE_ORDERS=(
    "1,12,25,50"
    "50,25,12,1"
)

RUN_ID="${MNEME_FORMAL_RUN_ID:-$(date -u +'%Y%m%dT%H%M%SZ')-$(uuidgen | tr '[:upper:]' '[:lower:]')}"
RUN_ROOT="$(realpath -m "$RAW_ROOT/$RUN_ID")"
SESSIONS_ROOT="$RUN_ROOT/sessions"
COMMANDS_FILE="$RUN_ROOT/commands.tsv"
RUN_ROOT_REPO_RELATIVE="$(realpath -m --relative-to="$REPO_ROOT" "$RUN_ROOT")"
if [[ "$RUN_ROOT_REPO_RELATIVE" == ".." || "$RUN_ROOT_REPO_RELATIVE" == ../* ]]; then
    RUN_ROOT_REPO_RELATIVE=""
fi

current_emulator_pid=""
current_serial=""
current_session_dir=""
current_session_id=""
current_phase="preflight"
failure_reason=""

fail() {
    failure_reason="$1"
    printf 'ERROR: %s\n' "$failure_reason" >&2
    exit 1
}

utc_now() {
    date -u +'%Y-%m-%dT%H:%M:%SZ'
}

sha256() {
    sha256sum "$1" | awk '{print $1}'
}

quote_command() {
    local quoted=""
    local argument
    for argument in "$@"; do
        printf -v argument '%q' "$argument"
        quoted+="${quoted:+ }$argument"
    done
    printf '%s\n' "$quoted"
}

append_command_record() {
    local scope="$1"
    local started_at="$2"
    local completed_at="$3"
    local status="$4"
    local command_text="$5"
    command_text="${command_text//$'\t'/ }"
    printf '%s\t%s\t%s\t%s\t%s\n' \
        "$scope" \
        "$started_at" \
        "$completed_at" \
        "$status" \
        "$command_text" \
        >>"$COMMANDS_FILE"
}

run_logged() {
    local scope="$1"
    local output_file="$2"
    shift 2
    local started_at
    local completed_at
    local status
    local command_text
    started_at="$(utc_now)"
    command_text="$(quote_command "$@")"
    set +e
    "$@" >"$output_file" 2>&1
    status="$?"
    set -e
    completed_at="$(utc_now)"
    append_command_record \
        "$scope" \
        "$started_at" \
        "$completed_at" \
        "$status" \
        "$command_text"
    return "$status"
}

config_cpu_cores() {
    case "$1" in
        cpu2_ram2gb | cpu2_ram6gb) printf '2\n' ;;
        cpu4_ram2gb | cpu4_ram6gb) printf '4\n' ;;
        *) fail "Unknown formal resource configuration: $1" ;;
    esac
}

config_ram_mb() {
    case "$1" in
        cpu2_ram2gb | cpu4_ram2gb) printf '2048\n' ;;
        cpu2_ram6gb | cpu4_ram6gb) printf '6144\n' ;;
        *) fail "Unknown formal resource configuration: $1" ;;
    esac
}

stop_emulator() {
    set +e
    if [[ -n "$current_serial" ]]; then
        "$ADB" -s "$current_serial" emu kill >/dev/null 2>&1
    fi
    if [[ -n "$current_emulator_pid" ]]; then
        for _ in $(seq 1 30); do
            if ! kill -0 "$current_emulator_pid" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$current_emulator_pid" 2>/dev/null; then
            kill "$current_emulator_pid" 2>/dev/null
        fi
        wait "$current_emulator_pid" 2>/dev/null
    fi
    current_emulator_pid=""
    current_serial=""
    set -e
}

pull_graph_artifacts_best_effort() {
    if [[ -z "$current_serial" || -z "$current_session_dir" ]]; then
        return
    fi
    local destination="$current_session_dir/graph_device_artifacts"
    mkdir -p "$destination"
    "$ADB" -s "$current_serial" pull \
        "$DEVICE_EVALUATION_DIR/." \
        "$destination/" \
        >>"$current_session_dir/graph_pull_cleanup.txt" \
        2>&1 || true
}

write_failure_record() {
    local exit_status="$1"
    if [[ -z "$current_session_dir" || -f "$current_session_dir/completed.json" || -f "$current_session_dir/failed.json" ]]; then
        return
    fi
    jq -n \
        --arg schema_version "android-formal-session-failure-v2" \
        --arg session_id "$current_session_id" \
        --arg phase "$current_phase" \
        --arg failed_at_utc "$(utc_now)" \
        --arg reason "${failure_reason:-unexpected command failure}" \
        --argjson exit_status "$exit_status" \
        '{
            schema_version: $schema_version,
            session_id: $session_id,
            status: "failed",
            phase: $phase,
            failed_at_utc: $failed_at_utc,
            exit_status: $exit_status,
            reason: $reason,
            automatic_retry_performed: false
        }' \
        >"$current_session_dir/failed.json" || true
}

write_experiment_failure_record() {
    local exit_status="$1"
    if [[ ! -d "$RUN_ROOT" || -f "$RUN_ROOT/experiment_completed.json" || -f "$RUN_ROOT/experiment_failed.json" ]]; then
        return
    fi
    jq -n \
        --arg schema_version "android-formal-experiment-failure-v2" \
        --arg run_id "$RUN_ID" \
        --arg phase "$current_phase" \
        --arg failed_at_utc "$(utc_now)" \
        --arg reason "${failure_reason:-unexpected command failure}" \
        --argjson exit_status "$exit_status" \
        '{
            schema_version: $schema_version,
            run_id: $run_id,
            status: "failed",
            phase: $phase,
            failed_at_utc: $failed_at_utc,
            exit_status: $exit_status,
            reason: $reason,
            automatic_retry_performed: false
        }' \
        >"$RUN_ROOT/experiment_failed.json" || true
}

cleanup() {
    local exit_status="$?"
    trap - EXIT INT TERM
    set +e
    if [[ "$exit_status" -ne 0 ]]; then
        pull_graph_artifacts_best_effort
        write_failure_record "$exit_status"
        write_experiment_failure_record "$exit_status"
    fi
    stop_emulator
    exit "$exit_status"
}

trap cleanup EXIT
trap 'failure_reason="interrupted by signal"; exit 130' INT TERM

wait_for_serial() {
    local elapsed=0
    while ((elapsed < 60)); do
        current_serial="$(
            "$ADB" devices |
                awk 'NR > 1 && $2 == "device" { print $1; exit }'
        )"
        if [[ -n "$current_serial" ]]; then
            return
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    fail "ADB did not expose the formal emulator within 60 seconds."
}

wait_for_boot() {
    local elapsed=0
    local boot_completed
    local boot_animation
    while ((elapsed < BOOT_TIMEOUT_SECONDS)); do
        boot_completed="$(
            "$ADB" -s "$current_serial" shell getprop sys.boot_completed 2>/dev/null |
                tr -d '\r'
        )"
        boot_animation="$(
            "$ADB" -s "$current_serial" shell getprop init.svc.bootanim 2>/dev/null |
                tr -d '\r'
        )"
        if [[ "$boot_completed" == "1" && "$boot_animation" == "stopped" ]]; then
            "$ADB" -s "$current_serial" shell input keyevent 82 >/dev/null 2>&1 || true
            sleep "$BOOT_STABILIZATION_SECONDS"
            return
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    fail "AVD did not complete a cold boot within ${BOOT_TIMEOUT_SECONDS}s."
}

host_load_one() {
    awk '{print $1}' /proc/loadavg
}

host_available_memory_bytes() {
    awk '/MemAvailable:/ {print $2 * 1024}' /proc/meminfo
}

capture_host_snapshot() {
    local destination="$1"
    {
        printf 'captured_at_utc=%s\n' "$(utc_now)"
        printf 'load_average='
        cat /proc/loadavg
        printf 'kernel='
        uname -a
        printf 'os_release:\n'
        sed -n '1,80p' /etc/os-release
        printf 'cpu:\n'
        lscpu
        printf 'memory:\n'
        free -b
        printf 'power:\n'
        for supply in /sys/class/power_supply/*; do
            [[ -d "$supply" ]] || continue
            printf '%s\n' "$supply"
            for field in type online status capacity; do
                if [[ -r "$supply/$field" ]]; then
                    printf '  %s=' "$field"
                    cat "$supply/$field"
                fi
            done
        done
        printf 'cpu_governors:\n'
        for governor in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
            [[ -r "$governor" ]] || continue
            printf '%s=' "$governor"
            cat "$governor"
        done
    } >"$destination"
}

copy_recent_startup_outputs() {
    local marker="$1"
    local destination="$2"
    [[ -d "$STARTUP_OUTPUT_ROOT" ]] || return 1
    mkdir -p "$destination"
    local copied=0
    local source
    local relative
    while IFS= read -r -d '' source; do
        relative="${source#"$STARTUP_OUTPUT_ROOT"/}"
        mkdir -p "$destination/$(dirname "$relative")"
        cp -p "$source" "$destination/$relative"
        copied=$((copied + 1))
    done < <(
        find "$STARTUP_OUTPUT_ROOT" -type f -newer "$marker" -print0 |
            sort -z
    )
    ((copied > 0))
}

verify_build_artifacts() {
    local actual
    actual="$(sha256 "$STARTUP_APP_APK_SOURCE")"
    [[ "$actual" == "$STARTUP_APP_APK_HASH" ]] ||
        fail "The startup app APK changed after the build was frozen."
    actual="$(sha256 "$STARTUP_BENCHMARK_APK_SOURCE")"
    [[ "$actual" == "$STARTUP_BENCHMARK_APK_HASH" ]] ||
        fail "The startup benchmark APK changed after the build was frozen."
    actual="$(sha256 "$GRAPH_APP_APK_SOURCE")"
    [[ "$actual" == "$GRAPH_APP_APK_HASH" ]] ||
        fail "The graph app APK changed after the build was frozen."
    actual="$(sha256 "$GRAPH_TEST_APK_SOURCE")"
    [[ "$actual" == "$GRAPH_TEST_APK_HASH" ]] ||
        fail "The graph test APK changed after the build was frozen."
}

verify_finish_provenance() {
    local current_revision
    local current_branch
    local untracked_path
    current_revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"
    current_branch="$(git -C "$REPO_ROOT" branch --show-current)"
    [[ "$current_revision" == "$SOURCE_REVISION" ]] ||
        fail "Repository HEAD changed during formal acquisition."
    [[ "$current_branch" == "$SOURCE_BRANCH" ]] ||
        fail "Repository branch changed during formal acquisition."
    git -C "$REPO_ROOT" diff --quiet -- ||
        fail "A tracked worktree file changed during formal acquisition."
    git -C "$REPO_ROOT" diff --cached --quiet -- ||
        fail "The Git index changed during formal acquisition."
    while IFS= read -r -d '' untracked_path; do
        if [[
            -z "$RUN_ROOT_REPO_RELATIVE" ||
                "$untracked_path" != "$RUN_ROOT_REPO_RELATIVE/"*
        ]]; then
            fail "Unrelated untracked file appeared during formal acquisition: $untracked_path"
        fi
    done < <(
        git -C "$REPO_ROOT" ls-files \
            --others \
            --exclude-standard \
            -z
    )
    [[ "$(sha256 "$0")" == "$RUNNER_SHA256" ]] ||
        fail "The formal runner changed during acquisition."
    [[ "$(sha256 "$ANALYZER")" == "$ANALYZER_SHA256" ]] ||
        fail "The formal analyzer changed during acquisition."
}

write_session_artifact_hashes() {
    local session_dir="$1"
    local output="$session_dir/artifact_hashes.json"
    local relative
    local artifact
    local digest
    local item_stream="$session_dir/.artifact_hash_items.jsonl"
    : >"$item_stream"
    while IFS= read -r -d '' artifact; do
        relative="${artifact#"$RUN_ROOT"/}"
        digest="$(sha256 "$artifact")"
        jq -cn \
            --arg key "$relative" \
            --arg value "$digest" \
            '{key: $key, value: $value}' \
            >>"$item_stream"
    done < <(
        find "$session_dir" \
            -type f \
            ! -name completed.json \
            ! -name failed.json \
            ! -name artifact_hashes.json \
            ! -name .artifact_hash_items.jsonl \
            ! -name startup_output_marker \
            -print0 |
            sort -z
    )
    jq -s 'map({(.key): .value}) | add // {}' "$item_stream" >"$output"
    rm -f "$item_stream"
}

record_experiment_manifest() {
    jq -n \
        --arg schema_version "android-formal-experiment-v2" \
        --arg run_id "$RUN_ID" \
        --arg started_at_utc "$EXPERIMENT_STARTED_AT" \
        --arg source_revision "$SOURCE_REVISION" \
        --arg source_branch "$SOURCE_BRANCH" \
        --arg runner_sha256 "$RUNNER_SHA256" \
        --arg analyzer_sha256 "$ANALYZER_SHA256" \
        --arg avd_name "$AVD_NAME" \
        --arg host_cpuset "$HOST_CPUSET" \
        --arg startup_app_sha256 "$STARTUP_APP_APK_HASH" \
        --arg startup_benchmark_sha256 "$STARTUP_BENCHMARK_APK_HASH" \
        --arg graph_app_sha256 "$GRAPH_APP_APK_HASH" \
        --arg graph_test_sha256 "$GRAPH_TEST_APK_HASH" \
        '{
            schema_version: $schema_version,
            run_id: $run_id,
            status: "collecting",
            started_at_utc: $started_at_utc,
            source_revision: $source_revision,
            source_branch: $source_branch,
            protocol: {
                design: "2x2 CPU x RAM with two order-reversed complementary blocks",
                block_orders: [
                    ["cpu2_ram2gb", "cpu2_ram6gb", "cpu4_ram6gb", "cpu4_ram2gb"],
                    ["cpu4_ram2gb", "cpu4_ram6gb", "cpu2_ram6gb", "cpu2_ram2gb"]
                ],
                graph_node_orders: [
                    [1, 12, 25, 50],
                    [50, 25, 12, 1]
                ],
                analysis_unit: "one separately cold-booted, wiped-data emulator session",
                sessions: 8,
                startup_raw_iterations_per_scenario: 6,
                startup_first_iteration_excluded: true,
                startup_retained_iterations_per_scenario: 5,
                graph_warmup_pairs_per_node_count: 1,
                graph_retained_pairs_per_node_count: 5,
                graph_retained_rows_per_session: 40
            },
            environment: {
                avd_name: $avd_name,
                host_cpuset: $host_cpuset,
                backend_used: false,
                live_credentials_required: false,
                startup_data_source: "benchmark-seeded production Room cache",
                graph_data_source: "deterministic bounded graph fixture",
                graph_debug_demo_token: "blank",
                network_endpoint: "unreachable loopback guard"
            },
            provenance: {
                runner_sha256: $runner_sha256,
                analyzer_sha256: $analyzer_sha256,
                startup_app_apk_sha256: $startup_app_sha256,
                startup_benchmark_apk_sha256: $startup_benchmark_sha256,
                graph_app_apk_sha256: $graph_app_sha256,
                graph_test_apk_sha256: $graph_test_sha256
            },
            automatic_retry_enabled: false
        }' \
        >"$RUN_ROOT/experiment_manifest.json"
}

[[ -x "$ADB" ]] || fail "ADB was not found under $ANDROID_SDK_ROOT."
[[ -x "$EMULATOR" ]] || fail "The Android emulator was not found under $ANDROID_SDK_ROOT."
[[ -x "$JAVA_HOME/bin/java" ]] || fail "JDK 17 was not found under $JAVA_HOME."
[[ -f "$ANALYZER" ]] || fail "The formal analyzer is missing: $ANALYZER"
for dependency in jq timeout sha256sum uuidgen flock taskset python3 git realpath uv; do
    command -v "$dependency" >/dev/null || fail "$dependency is required."
done
for inherited_java_option in \
    JAVA_TOOL_OPTIONS \
    JDK_JAVA_OPTIONS \
    _JAVA_OPTIONS \
    JAVA_OPTS \
    GRADLE_OPTS; do
    if [[ -v "$inherited_java_option" ]]; then
        fail "$inherited_java_option must be unset so retained Gradle logs cannot expose inherited options."
    fi
done
unset \
    MNEME_API_BASE_URL \
    MNEME_DEMO_TOKEN \
    ORG_GRADLE_PROJECT_MNEME_API_BASE_URL \
    ORG_GRADLE_PROJECT_MNEME_DEMO_TOKEN
[[ "$RUN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
    fail "MNEME_FORMAL_RUN_ID must contain only letters, digits, dots, underscores, or hyphens."
"$EMULATOR" -list-avds | grep -Fxq "$AVD_NAME" ||
    fail "The dedicated formal AVD is unavailable: $AVD_NAME"

exec 9>"/tmp/mneme-android-formal-resource.lock"
flock -n 9 || fail "Another formal Android resource run holds the experiment lock."

mapfile -t connected_devices < <(
    "$ADB" devices |
        awk 'NR > 1 && $2 == "device" {print $1}'
)
[[ "${#connected_devices[@]}" -eq 0 ]] ||
    fail "Stop or disconnect every Android device before the formal run."
if pgrep -f "$ANDROID_SDK_ROOT/emulator/qemu" >/dev/null; then
    fail "An Android emulator process is already running."
fi
taskset -c "$HOST_CPUSET" true ||
    fail "MNEME_FORMAL_HOST_CPUSET is not valid on this host: $HOST_CPUSET"

SOURCE_REVISION="$(git -C "$REPO_ROOT" rev-parse HEAD)"
SOURCE_BRANCH="$(git -C "$REPO_ROOT" branch --show-current)"
if [[ -n "$(git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all)" ]]; then
    fail "Formal measurement requires a clean worktree, including tracked runner/analyzer files."
fi
[[ ! -e "$RUN_ROOT" ]] || fail "Run root already exists and will not be overwritten: $RUN_ROOT"

mkdir -p "$SESSIONS_ROOT"
printf 'scope\tstarted_at_utc\tcompleted_at_utc\texit_status\tcommand\n' >"$COMMANDS_FILE"
EXPERIMENT_STARTED_AT="$(utc_now)"
RUNNER_SHA256="$(sha256 "$0")"
ANALYZER_SHA256="$(sha256 "$ANALYZER")"
capture_host_snapshot "$RUN_ROOT/host_environment_before.txt"

export ANDROID_HOME="$ANDROID_SDK_ROOT"
export ANDROID_SDK_ROOT
export JAVA_HOME

current_phase="build"
BUILD_LOG="$RUN_ROOT/build.txt"
if ! run_logged \
    build \
    "$BUILD_LOG" \
    timeout 20m \
    "$ANDROID_DIR/gradlew" \
    -p "$ANDROID_DIR" \
    --no-daemon \
    --no-configuration-cache \
    "-PMNEME_API_BASE_URL=$CONTROLLED_UNREACHABLE_BASE_URL" \
    "-PMNEME_DEMO_TOKEN=" \
    "${BUILD_TASKS[@]}"; then
    fail "The frozen formal build failed; see $BUILD_LOG."
fi

for artifact in \
    "$STARTUP_APP_APK_SOURCE" \
    "$STARTUP_BENCHMARK_APK_SOURCE" \
    "$GRAPH_APP_APK_SOURCE" \
    "$GRAPH_TEST_APK_SOURCE"; do
    [[ -f "$artifact" ]] || fail "Expected formal APK was not built: $artifact"
done

STARTUP_APP_APK_HASH="$(sha256 "$STARTUP_APP_APK_SOURCE")"
STARTUP_BENCHMARK_APK_HASH="$(sha256 "$STARTUP_BENCHMARK_APK_SOURCE")"
GRAPH_APP_APK_HASH="$(sha256 "$GRAPH_APP_APK_SOURCE")"
GRAPH_TEST_APK_HASH="$(sha256 "$GRAPH_TEST_APK_SOURCE")"
jq -n \
    --arg startup_app_path "${STARTUP_APP_APK_SOURCE#"$REPO_ROOT"/}" \
    --arg startup_app_sha256 "$STARTUP_APP_APK_HASH" \
    --arg startup_benchmark_path "${STARTUP_BENCHMARK_APK_SOURCE#"$REPO_ROOT"/}" \
    --arg startup_benchmark_sha256 "$STARTUP_BENCHMARK_APK_HASH" \
    --arg graph_app_path "${GRAPH_APP_APK_SOURCE#"$REPO_ROOT"/}" \
    --arg graph_app_sha256 "$GRAPH_APP_APK_HASH" \
    --arg graph_test_path "${GRAPH_TEST_APK_SOURCE#"$REPO_ROOT"/}" \
    --arg graph_test_sha256 "$GRAPH_TEST_APK_HASH" \
    '{
        startup_app: {
            path: $startup_app_path,
            sha256: $startup_app_sha256
        },
        startup_benchmark: {
            path: $startup_benchmark_path,
            sha256: $startup_benchmark_sha256
        },
        graph_app: {
            path: $graph_app_path,
            sha256: $graph_app_sha256
        },
        graph_test: {
            path: $graph_test_path,
            sha256: $graph_test_sha256
        },
        apks_retained: false,
        live_credentials_embedded: false,
        note: "Only paths and hashes are retained; the formal protocol does not use a backend."
    }' \
    >"$RUN_ROOT/build_artifacts.json"
verify_build_artifacts
record_experiment_manifest

for block_index in "${!BLOCK_ORDERS[@]}"; do
    block_number=$((block_index + 1))
    read -r -a order <<<"${BLOCK_ORDERS[$block_index]}"
    node_order="${NODE_ORDERS[$block_index]}"
    for position_index in "${!order[@]}"; do
        position=$((position_index + 1))
        config_id="${order[$position_index]}"
        cpu_cores="$(config_cpu_cores "$config_id")"
        ram_mb="$(config_ram_mb "$config_id")"
        current_session_id="$(uuidgen | tr '[:upper:]' '[:lower:]')"
        current_session_dir="$SESSIONS_ROOT/block-$(printf '%02d' "$block_number")-position-$(printf '%02d' "$position")-$config_id"
        mkdir -p "$current_session_dir"
        session_started_at="$(utc_now)"
        host_load_before="$(host_load_one)"
        host_memory_before="$(host_available_memory_bytes)"
        capture_host_snapshot "$current_session_dir/host_before.txt"

        current_phase="emulator_boot"
        emulator_command=(
            taskset -c "$HOST_CPUSET"
            "$EMULATOR"
            -avd "$AVD_NAME"
            -cores "$cpu_cores"
            -memory "$ram_mb"
            -wipe-data
            -no-window
            -no-audio
            -no-boot-anim
            -no-snapshot
            -gpu swiftshader_indirect
        )
        emulator_started_at="$(utc_now)"
        "${emulator_command[@]}" >"$current_session_dir/emulator_output.txt" 2>&1 &
        current_emulator_pid="$!"
        append_command_record \
            emulator_start \
            "$emulator_started_at" \
            "$(utc_now)" \
            0 \
            "$(quote_command "${emulator_command[@]}")"
        wait_for_serial
        wait_for_boot

        boot_id="$(
            "$ADB" -s "$current_serial" shell cat /proc/sys/kernel/random/boot_id |
                tr -d '\r'
        )"
        runtime_cpu_cores="$(
            "$ADB" -s "$current_serial" shell nproc |
                tr -d '\r'
        )"
        runtime_memory_kb="$(
            "$ADB" -s "$current_serial" shell cat /proc/meminfo |
                awk '/MemTotal:/ {print $2}' |
                tr -d '\r'
        )"
        runtime_page_size="$(
            "$ADB" -s "$current_serial" shell getconf PAGE_SIZE |
                tr -d '\r'
        )"
        screen_size="$(
            "$ADB" -s "$current_serial" shell wm size |
                tail -n 1 |
                sed 's/.*: //' |
                tr -d '\r'
        )"
        screen_density="$(
            "$ADB" -s "$current_serial" shell wm density |
                tail -n 1 |
                awk '{print $NF}' |
                tr -d '\r'
        )"
        build_fingerprint="$(
            "$ADB" -s "$current_serial" shell getprop ro.build.fingerprint |
                tr -d '\r'
        )"
        webview_package="$(
            "$ADB" -s "$current_serial" shell cmd webviewupdate getCurrentWebViewPackage 2>&1 |
                tr -d '\r'
        )"
        [[ "$runtime_cpu_cores" -eq "$cpu_cores" ]] ||
            fail "Guest nproc=$runtime_cpu_cores, expected $cpu_cores."
        if [[ "$ram_mb" -eq 2048 ]]; then
            ((runtime_memory_kb >= 1500000 && runtime_memory_kb <= 2400000)) ||
                fail "Guest MemTotal=$runtime_memory_kb KiB is outside the 2 GiB cell."
        else
            ((runtime_memory_kb >= 5000000 && runtime_memory_kb <= 6600000)) ||
                fail "Guest MemTotal=$runtime_memory_kb KiB is outside the 6 GiB cell."
        fi

        "$ADB" -s "$current_serial" shell settings put global window_animation_scale 0
        "$ADB" -s "$current_serial" shell settings put global transition_animation_scale 0
        "$ADB" -s "$current_serial" shell settings put global animator_duration_scale 0
        "$ADB" -s "$current_serial" shell svc power stayon true

        jq -n \
            --arg schema_version "android-formal-session-v2" \
            --arg session_id "$current_session_id" \
            --arg run_id "$RUN_ID" \
            --arg config_id "$config_id" \
            --arg started_at_utc "$session_started_at" \
            --arg source_revision "$SOURCE_REVISION" \
            --arg source_branch "$SOURCE_BRANCH" \
            --arg avd_name "$AVD_NAME" \
            --arg emulator_pid "$current_emulator_pid" \
            --arg serial "$current_serial" \
            --arg boot_id "$boot_id" \
            --arg build_fingerprint "$build_fingerprint" \
            --arg webview_package "$webview_package" \
            --arg host_cpuset "$HOST_CPUSET" \
            --arg screen_size "$screen_size" \
            --argjson block "$block_number" \
            --argjson sequence_position "$position" \
            --argjson requested_cpu_cores "$cpu_cores" \
            --argjson requested_ram_mb "$ram_mb" \
            --argjson runtime_cpu_cores "$runtime_cpu_cores" \
            --argjson runtime_memory_kb "$runtime_memory_kb" \
            --argjson runtime_page_size_bytes "$runtime_page_size" \
            --argjson screen_density_dpi "$screen_density" \
            --argjson host_load_one_before "$host_load_before" \
            --argjson host_available_memory_bytes_before "$host_memory_before" \
            --arg node_order "$node_order" \
            --arg runner_sha256 "$RUNNER_SHA256" \
            --arg analyzer_sha256 "$ANALYZER_SHA256" \
            --arg startup_app_sha256 "$STARTUP_APP_APK_HASH" \
            --arg startup_benchmark_sha256 "$STARTUP_BENCHMARK_APK_HASH" \
            --arg graph_app_sha256 "$GRAPH_APP_APK_HASH" \
            --arg graph_test_sha256 "$GRAPH_TEST_APK_HASH" \
            '{
                schema_version: $schema_version,
                session_id: $session_id,
                run_id: $run_id,
                status: "collecting",
                block: $block,
                sequence_position: $sequence_position,
                config_id: $config_id,
                started_at_utc: $started_at_utc,
                source_revision: $source_revision,
                source_branch: $source_branch,
                avd_name: $avd_name,
                emulator_pid: $emulator_pid,
                serial: $serial,
                boot_id: $boot_id,
                cold_boot_and_wipe_data: true,
                requested_cpu_cores: $requested_cpu_cores,
                requested_ram_mb: $requested_ram_mb,
                runtime_cpu_cores: $runtime_cpu_cores,
                runtime_memory_kb: $runtime_memory_kb,
                runtime_page_size_bytes: $runtime_page_size_bytes,
                build_fingerprint: $build_fingerprint,
                webview_package: $webview_package,
                backend_used: false,
                startup_data_source: "benchmark-seeded production Room cache",
                graph_data_source: "deterministic bounded graph fixture",
                screen_size: $screen_size,
                screen_density_dpi: $screen_density_dpi,
                host_cpuset: $host_cpuset,
                host_load_one_before: $host_load_one_before,
                host_available_memory_bytes_before: $host_available_memory_bytes_before,
                graph_node_order: ($node_order | split(",") | map(tonumber)),
                provenance: {
                    runner_sha256: $runner_sha256,
                    analyzer_sha256: $analyzer_sha256,
                    startup_app_apk_sha256: $startup_app_sha256,
                    startup_benchmark_apk_sha256: $startup_benchmark_sha256,
                    graph_app_apk_sha256: $graph_app_sha256,
                    graph_test_apk_sha256: $graph_test_sha256
                }
            }' \
            >"$current_session_dir/session_manifest.json"

        current_phase="startup_benchmark"
        verify_build_artifacts
        startup_marker="$current_session_dir/startup_output_marker"
        touch "$startup_marker"
        startup_stdout="$current_session_dir/startup_benchmark.txt"
        export ANDROID_SERIAL="$current_serial"
        if run_logged \
            startup_benchmark \
            "$startup_stdout" \
            timeout "$STARTUP_TIMEOUT" \
            "$ANDROID_DIR/gradlew" \
            -p "$ANDROID_DIR" \
            --offline \
            --no-daemon \
            --no-configuration-cache \
            "-PMNEME_API_BASE_URL=$CONTROLLED_UNREACHABLE_BASE_URL" \
            "-PMNEME_DEMO_TOKEN=" \
            "$STARTUP_CONNECTED_TASK" \
            "-Pandroid.testInstrumentationRunnerArguments.class=$STARTUP_TEST_CLASS"; then
            startup_status=0
        else
            startup_status="$?"
        fi
        unset ANDROID_SERIAL
        startup_raw="$current_session_dir/startup_raw"
        if ! copy_recent_startup_outputs "$startup_marker" "$startup_raw"; then
            fail "No new native Macrobenchmark output was retained for $current_session_id."
        fi
        verify_build_artifacts
        startup_extract_command=(
            python3 "$ANALYZER"
            extract-startup
            --benchmark-data "$startup_raw"
            --session-id "$current_session_id"
            --benchmark-exit-status "$startup_status"
            --output "$current_session_dir/startup_measurements.csv"
        )
        startup_extract_command+=(
            --cold-metric "$STARTUP_COLD_METRIC"
            --resume-metric "$STARTUP_RESUME_METRIC"
        )
        if ! run_logged \
            startup_extract \
            "$current_session_dir/startup_extract.txt" \
            "${startup_extract_command[@]}"; then
            fail "Native Macrobenchmark startup extraction failed."
        fi
        if [[ "$startup_status" -ne 0 ]]; then
            fail "Startup Macrobenchmark failed with status $startup_status after raw output retention."
        fi

        current_phase="graph_instrumentation"
        if ! run_logged \
            graph_app_install \
            "$current_session_dir/graph_app_install.txt" \
            "$ADB" -s "$current_serial" install -r -t "$GRAPH_APP_APK_SOURCE"; then
            fail "Graph app APK installation failed."
        fi
        if ! run_logged \
            graph_test_install \
            "$current_session_dir/graph_test_install.txt" \
            "$ADB" -s "$current_serial" install -r -t "$GRAPH_TEST_APK_SOURCE"; then
            fail "Graph test APK installation failed."
        fi
        if ! run_logged \
            graph_app_clear \
            "$current_session_dir/graph_app_clear.txt" \
            "$ADB" -s "$current_serial" shell pm clear com.mneme.app; then
            fail "Graph app data clearing failed."
        fi
        graph_clear_result="$(
            tr -d '\r\n' <"$current_session_dir/graph_app_clear.txt"
        )"
        [[ "$graph_clear_result" == "Success" ]] ||
            fail "Graph app data clearing did not report exact success."
        if ! run_logged \
            graph_artifact_reset \
            "$current_session_dir/graph_artifact_reset.txt" \
            "$ADB" -s "$current_serial" shell rm -rf "$DEVICE_EVALUATION_DIR"; then
            fail "Graph artifact directory reset failed."
        fi
        graph_stdout="$current_session_dir/graph_instrumentation.txt"
        if run_logged \
            graph_instrumentation \
            "$graph_stdout" \
            timeout "$GRAPH_TIMEOUT" \
            "$ADB" -s "$current_serial" shell am instrument \
            -w \
            -r \
            -e class "$GRAPH_TEST_CLASS" \
            -e e4SessionId "$current_session_id" \
            -e e4GraphNodeOrder "$node_order" \
            -e e4GraphWarmupPairs 1 \
            -e e4GraphMeasuredPairs 5 \
            "$GRAPH_TEST_RUNNER"; then
            graph_status=0
        else
            graph_status="$?"
        fi

        current_phase="graph_artifact_pull"
        graph_artifacts="$current_session_dir/graph_device_artifacts"
        mkdir -p "$graph_artifacts"
        if run_logged \
            graph_pull \
            "$current_session_dir/graph_pull.txt" \
            "$ADB" -s "$current_serial" pull \
            "$DEVICE_EVALUATION_DIR/." \
            "$graph_artifacts/"; then
            graph_pull_status=0
        else
            graph_pull_status="$?"
        fi
        graph_device_csv="$graph_artifacts/graph_measurements.csv"
        if [[ -f "$graph_device_csv" ]]; then
            cp -p "$graph_device_csv" "$current_session_dir/graph_measurements.csv"
        fi
        if [[ "$graph_status" -ne 0 ]]; then
            fail "Graph instrumentation failed with status $graph_status after device artifact pull."
        fi
        if [[ "$graph_pull_status" -ne 0 || ! -f "$current_session_dir/graph_measurements.csv" ]]; then
            fail "Graph artifacts were not pulled successfully."
        fi
        tr -d '\r' <"$graph_stdout" | grep -Fxq 'OK (1 test)' ||
            fail "Graph instrumentation did not report exactly one passing test."

        current_phase="session_validation"
        if ! run_logged \
            session_validation \
            "$current_session_dir/session_validation.txt" \
            python3 "$ANALYZER" \
            validate-session \
            --startup-csv "$current_session_dir/startup_measurements.csv" \
            --graph-csv "$current_session_dir/graph_measurements.csv" \
            --session-id "$current_session_id" \
            --node-order "$node_order" \
            --require-success; then
            fail "The exact 10-row startup and 40-row graph contracts did not validate."
        fi

        "$ADB" -s "$current_serial" shell am force-stop com.mneme.app >/dev/null 2>&1 || true
        stop_emulator
        capture_host_snapshot "$current_session_dir/host_after.txt"
        host_load_after="$(host_load_one)"
        host_memory_after="$(host_available_memory_bytes)"
        session_completed_at="$(utc_now)"
        write_session_artifact_hashes "$current_session_dir"
        jq -n \
            --arg schema_version "android-formal-session-completion-v2" \
            --arg session_id "$current_session_id" \
            --arg completed_at_utc "$session_completed_at" \
            --argjson startup_rows 10 \
            --argjson graph_rows 40 \
            --argjson host_load_one_after "$host_load_after" \
            --argjson host_available_memory_bytes_after "$host_memory_after" \
            --slurpfile artifact_sha256 "$current_session_dir/artifact_hashes.json" \
            '{
                schema_version: $schema_version,
                session_id: $session_id,
                status: "completed",
                completed_at_utc: $completed_at_utc,
                retained_startup_rows: $startup_rows,
                retained_graph_rows: $graph_rows,
                host_load_one_after: $host_load_one_after,
                host_available_memory_bytes_after: $host_available_memory_bytes_after,
                artifact_sha256: $artifact_sha256[0],
                failed_samples_removed: 0,
                automatic_retry_performed: false
            }' \
            >"$current_session_dir/completed.json"
        printf 'Completed formal block %s/2, position %s/4: %s\n' \
            "$block_number" \
            "$position" \
            "$config_id"
        current_session_dir=""
        current_session_id=""
    done
done

current_phase="formal_analysis"
if ! run_logged \
    formal_analysis \
    "$RUN_ROOT/analysis.txt" \
    timeout "$SESSION_TIMEOUT" \
    "$ANALYZER" analyze --run-root "$RUN_ROOT"; then
    fail "Formal descriptive analysis failed after raw data collection."
fi

capture_host_snapshot "$RUN_ROOT/host_environment_after.txt"
current_phase="final_provenance_check"
verify_build_artifacts
verify_finish_provenance
jq -n \
    --arg schema_version "android-formal-experiment-completion-v2" \
    --arg run_id "$RUN_ID" \
    --arg completed_at_utc "$(utc_now)" \
    --argjson sessions 8 \
    '{
        schema_version: $schema_version,
        run_id: $run_id,
        status: "completed",
        completed_at_utc: $completed_at_utc,
        completed_sessions: $sessions,
        automatic_retry_performed: false
    }' \
    >"$RUN_ROOT/experiment_completed.json"

printf 'Formal Android resource matrix completed under %s\n' "$RUN_ROOT"
