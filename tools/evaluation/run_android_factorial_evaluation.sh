#!/usr/bin/env bash

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ANDROID_DIR="$REPO_ROOT/android"
EVALUATION_DIR="$REPO_ROOT/docs/evaluation/android-factorial"
RAW_ROOT="$EVALUATION_DIR/raw"
ANDROID_SDK_ROOT="${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}"
JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
ADB="$ANDROID_SDK_ROOT/platform-tools/adb"
EMULATOR="$ANDROID_SDK_ROOT/emulator/emulator"
AVD_NAME="${MNEME_FACTORIAL_AVD:-Mneme_Factorial_API_34_Pixel6}"
RESUME="${MNEME_FACTORIAL_RESUME:-false}"
BOOT_TIMEOUT_SECONDS="${MNEME_FACTORIAL_BOOT_TIMEOUT_SECONDS:-240}"
INSTRUMENTATION_TIMEOUT="${MNEME_FACTORIAL_INSTRUMENTATION_TIMEOUT:-15m}"

CONFIG_IDS=(
    "cpu2_ram2gb"
    "cpu2_ram6gb"
    "cpu4_ram2gb"
    "cpu4_ram6gb"
)
BLOCK_ORDERS=(
    "cpu2_ram2gb cpu2_ram6gb cpu4_ram6gb cpu4_ram2gb"
    "cpu2_ram6gb cpu4_ram2gb cpu2_ram2gb cpu4_ram6gb"
    "cpu4_ram2gb cpu4_ram6gb cpu2_ram6gb cpu2_ram2gb"
    "cpu4_ram6gb cpu2_ram2gb cpu4_ram2gb cpu2_ram6gb"
)

current_emulator_pid=""
current_serial=""

fail() {
    printf 'ERROR: %s\n' "$1" >&2
    exit 1
}

config_cpu_cores() {
    case "$1" in
        cpu2_ram2gb | cpu2_ram6gb) printf '2\n' ;;
        cpu4_ram2gb | cpu4_ram6gb) printf '4\n' ;;
        *) fail "Unknown factorial configuration: $1" ;;
    esac
}

config_ram_mb() {
    case "$1" in
        cpu2_ram2gb | cpu4_ram2gb) printf '2048\n' ;;
        cpu2_ram6gb | cpu4_ram6gb) printf '6144\n' ;;
        *) fail "Unknown factorial configuration: $1" ;;
    esac
}

stop_emulator() {
    if [[ -n "$current_serial" ]]; then
        "$ADB" -s "$current_serial" emu kill >/dev/null 2>&1 || true
    fi
    if [[ -n "$current_emulator_pid" ]]; then
        for _ in $(seq 1 30); do
            if ! kill -0 "$current_emulator_pid" 2>/dev/null; then
                break
            fi
            sleep 1
        done
        if kill -0 "$current_emulator_pid" 2>/dev/null; then
            kill "$current_emulator_pid" 2>/dev/null || true
        fi
        wait "$current_emulator_pid" 2>/dev/null || true
    fi
    current_emulator_pid=""
    current_serial=""
}

trap stop_emulator EXIT INT TERM

[[ "$RESUME" == "true" || "$RESUME" == "false" ]] ||
    fail "MNEME_FACTORIAL_RESUME must be true or false."
[[ -x "$ADB" ]] || fail "adb was not found under $ANDROID_SDK_ROOT."
[[ -x "$EMULATOR" ]] || fail "emulator was not found under $ANDROID_SDK_ROOT."
[[ -x "$JAVA_HOME/bin/java" ]] || fail "JDK 17 was not found under $JAVA_HOME."
command -v jq >/dev/null || fail "jq is required."
command -v timeout >/dev/null || fail "GNU timeout is required."
"$EMULATOR" -list-avds | grep -Fxq "$AVD_NAME" ||
    fail "The dedicated factorial AVD is unavailable: $AVD_NAME"

mapfile -t connected_devices < <("$ADB" devices | awk 'NR > 1 && $2 == "device" { print $1 }')
[[ "${#connected_devices[@]}" -eq 0 ]] ||
    fail "Disconnect or stop existing Android devices before running the factorial experiment."

if [[ "$RESUME" == "false" ]]; then
    rm -rf "$RAW_ROOT"
fi
mkdir -p "$RAW_ROOT"

jq -n \
    --arg schema_version "android-factorial-design-v1" \
    --arg avd_name "$AVD_NAME" \
    --arg android_system_image "system-images/android-34/google_apis/x86_64/" \
    --arg device_profile "Pixel 6" \
    --arg screen "1080x2400 at 420 dpi" \
    --arg application_heap "228 MiB" \
    --argjson independent_blocks 4 \
    --argjson samples_per_session 810 \
    '{
        schema_version: $schema_version,
        design: "2x2 factorial with four counterbalanced independent blocks",
        factors: {
            cpu_cores: [2, 4],
            ram_mb: [2048, 6144]
        },
        controlled_environment: {
            avd_name: $avd_name,
            android_system_image: $android_system_image,
            device_profile: $device_profile,
            screen: $screen,
            application_heap: $application_heap,
            cold_boot_and_wipe_data_each_session: true,
            external_backend_used: false
        },
        independent_blocks: $independent_blocks,
        samples_per_session: $samples_per_session,
        block_orders: [
            ["cpu2_ram2gb", "cpu2_ram6gb", "cpu4_ram6gb", "cpu4_ram2gb"],
            ["cpu2_ram6gb", "cpu4_ram2gb", "cpu2_ram2gb", "cpu4_ram6gb"],
            ["cpu4_ram2gb", "cpu4_ram6gb", "cpu2_ram6gb", "cpu2_ram2gb"],
            ["cpu4_ram6gb", "cpu2_ram2gb", "cpu4_ram2gb", "cpu2_ram6gb"]
        ],
        interpretation_boundary: "Per-session summaries are the independent units; within-session samples are repeated measurements."
    }' \
    >"$EVALUATION_DIR/design.json"

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

APP_APK="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
TEST_APK="$ANDROID_DIR/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
[[ -f "$APP_APK" ]] || fail "Application APK was not built."
[[ -f "$TEST_APK" ]] || fail "Instrumentation APK was not built."

wait_for_boot() {
    local elapsed=0
    while (( elapsed < BOOT_TIMEOUT_SECONDS )); do
        if [[ "$("$ADB" -s "$current_serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" == "1" ]]; then
            "$ADB" -s "$current_serial" shell input keyevent 82 >/dev/null 2>&1 || true
            return
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    fail "AVD did not boot within ${BOOT_TIMEOUT_SECONDS}s: $current_serial"
}

run_instrumentation() {
    local classes="$1"
    local output_file="$2"
    local expected_tests="$3"
    set +e
    timeout "$INSTRUMENTATION_TIMEOUT" \
        "$ADB" -s "$current_serial" shell am instrument \
        -w \
        -r \
        -e class "$classes" \
        com.mneme.app.test/androidx.test.runner.AndroidJUnitRunner \
        >"$output_file" 2>&1
    local status="$?"
    set -e
    if [[ "$status" -ne 0 ]]; then
        tail -n 80 "$output_file" >&2 || true
        fail "Instrumentation failed with status $status; see $output_file."
    fi
    grep -Eq "^OK \\(${expected_tests} tests?\\)$" "$output_file" || {
        tail -n 80 "$output_file" >&2 || true
        fail "Instrumentation did not report ${expected_tests} passing tests; see $output_file."
    }
}

measure_launch_pair() {
    local iteration="$1"
    local record="$2"
    local startup_file="$3"
    local cold_output
    local warm_output
    local cold_state
    local cold_total
    local cold_wait
    local warm_state
    local warm_total
    local warm_wait

    "$ADB" -s "$current_serial" shell am force-stop com.mneme.app
    cold_output="$("$ADB" -s "$current_serial" shell am start -W -n com.mneme.app/.MainActivity)"
    cold_state="$(awk -F': ' '$1 == "LaunchState" { print $2 }' <<<"$cold_output")"
    cold_total="$(awk -F': ' '$1 == "TotalTime" { print $2 }' <<<"$cold_output")"
    cold_wait="$(awk -F': ' '$1 == "WaitTime" { print $2 }' <<<"$cold_output")"

    "$ADB" -s "$current_serial" shell input keyevent 3
    sleep 0.2
    warm_output="$("$ADB" -s "$current_serial" shell am start -W -n com.mneme.app/.MainActivity)"
    warm_state="$(awk -F': ' '$1 == "LaunchState" { print $2 }' <<<"$warm_output")"
    warm_total="$(awk -F': ' '$1 == "TotalTime" { print $2 }' <<<"$warm_output")"
    warm_wait="$(awk -F': ' '$1 == "WaitTime" { print $2 }' <<<"$warm_output")"

    if [[ "$record" == "true" ]]; then
        printf 'startup,cold_process,%s,%s,%s,%s,%s,%s\n' \
            "$iteration" "$cold_state" "$cold_total" "$cold_wait" \
            "$([[ -n "$cold_wait" ]] && printf true || printf false)" \
            'main_activity_wait_time_present' \
            >>"$startup_file"
        printf 'startup,warm_task_resume,%s,%s,%s,%s,%s,%s\n' \
            "$iteration" "$warm_state" "$warm_total" "$warm_wait" \
            "$([[ -n "$warm_wait" ]] && printf true || printf false)" \
            'main_activity_wait_time_present' \
            >>"$startup_file"
    fi
    "$ADB" -s "$current_serial" shell input keyevent 3
}

session_is_complete() {
    local run_dir="$1"
    [[ -f "$run_dir/completed.json" ]] &&
        [[ -f "$run_dir/app_start_measurements.csv" ]] &&
        [[ -f "$run_dir/state_measurements.csv" ]] &&
        [[ -f "$run_dir/graph_measurements.csv" ]] &&
        [[ -f "$run_dir/graph_state_measurements.csv" ]] &&
        [[ -f "$run_dir/event_sync_measurements.csv" ]] &&
        [[ -f "$run_dir/environment.json" ]] &&
        [[ -f "$run_dir/instrumentation_measurement.txt" ]]
}

for block_index in "${!BLOCK_ORDERS[@]}"; do
    block_number="$((block_index + 1))"
    read -r -a order <<<"${BLOCK_ORDERS[$block_index]}"
    for position_index in "${!order[@]}"; do
        position="$((position_index + 1))"
        config_id="${order[$position_index]}"
        cpu_cores="$(config_cpu_cores "$config_id")"
        ram_mb="$(config_ram_mb "$config_id")"
        run_dir="$RAW_ROOT/$config_id/run-$(printf '%02d' "$block_number")"

        if [[ "$RESUME" == "true" ]] && session_is_complete "$run_dir"; then
            printf 'Skipping completed block %s position %s: %s\n' \
                "$block_number" "$position" "$config_id"
            continue
        fi
        if [[ -e "$run_dir" ]]; then
            fail "Incomplete session artifacts already exist and were preserved: $run_dir"
        fi
        mkdir -p "$run_dir"

        printf 'Starting block %s/4 position %s/4: %s (%s cores, %s MiB RAM)\n' \
            "$block_number" "$position" "$config_id" "$cpu_cores" "$ram_mb"
        session_started_at="$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
        "$EMULATOR" \
            -avd "$AVD_NAME" \
            -cores "$cpu_cores" \
            -memory "$ram_mb" \
            -wipe-data \
            -no-window \
            -no-audio \
            -no-boot-anim \
            -no-snapshot \
            -gpu swiftshader_indirect \
            >"$run_dir/emulator.log" 2>&1 &
        current_emulator_pid="$!"

        for _ in $(seq 1 60); do
            current_serial="$("$ADB" devices | awk 'NR > 1 && $2 == "device" { print $1; exit }')"
            [[ -n "$current_serial" ]] && break
            sleep 1
        done
        [[ -n "$current_serial" ]] || fail "adb did not expose the AVD within 60 seconds."
        wait_for_boot

        runtime_cpu_cores="$("$ADB" -s "$current_serial" shell nproc | tr -d '\r')"
        runtime_memory_kb="$("$ADB" -s "$current_serial" shell cat /proc/meminfo | awk '/MemTotal/ { print $2 }' | tr -d '\r')"
        runtime_page_size="$("$ADB" -s "$current_serial" shell getconf PAGE_SIZE | tr -d '\r')"
        screen_size="$("$ADB" -s "$current_serial" shell wm size | tail -n 1 | sed 's/.*: //' | tr -d '\r')"
        screen_density="$("$ADB" -s "$current_serial" shell wm density | tail -n 1 | awk '{ print $NF }' | tr -d '\r')"
        [[ "$runtime_cpu_cores" -eq "$cpu_cores" ]] ||
            fail "Requested $cpu_cores cores but the guest reported $runtime_cpu_cores."

        jq -n \
            --arg schema_version "android-factorial-session-v1" \
            --arg config_id "$config_id" \
            --arg avd_name "$AVD_NAME" \
            --arg started_at_utc "$session_started_at" \
            --arg repository_revision "$(git -C "$REPO_ROOT" rev-parse HEAD)" \
            --arg branch "$(git -C "$REPO_ROOT" branch --show-current)" \
            --arg screen_size "$screen_size" \
            --argjson block "$block_number" \
            --argjson sequence_position "$position" \
            --argjson requested_cpu_cores "$cpu_cores" \
            --argjson requested_ram_mb "$ram_mb" \
            --argjson runtime_cpu_cores "$runtime_cpu_cores" \
            --argjson runtime_memory_kb "$runtime_memory_kb" \
            --argjson runtime_page_size_bytes "$runtime_page_size" \
            --argjson screen_density_dpi "$screen_density" \
            '{
                schema_version: $schema_version,
                config_id: $config_id,
                block: $block,
                sequence_position: $sequence_position,
                avd_name: $avd_name,
                started_at_utc: $started_at_utc,
                repository_revision: $repository_revision,
                branch: $branch,
                requested_cpu_cores: $requested_cpu_cores,
                requested_ram_mb: $requested_ram_mb,
                runtime_cpu_cores: $runtime_cpu_cores,
                runtime_memory_kb: $runtime_memory_kb,
                runtime_page_size_bytes: $runtime_page_size_bytes,
                screen_size: $screen_size,
                screen_density_dpi: $screen_density_dpi,
                android_system_image: "android-34/google_apis/x86_64",
                device_profile: "Pixel 6",
                configured_application_heap_mb: 228,
                cold_boot_and_wipe_data: true,
                external_backend_used: false,
                credentials_retained: false
            }' \
            >"$run_dir/run_manifest.json"

        "$ADB" -s "$current_serial" install -r "$APP_APK" >/dev/null
        "$ADB" -s "$current_serial" install -r "$TEST_APK" >/dev/null
        "$ADB" -s "$current_serial" shell pm clear com.mneme.app >/dev/null
        "$ADB" -s "$current_serial" shell rm -rf \
            /sdcard/Android/data/com.mneme.app/files/e4-evaluation

        startup_file="$run_dir/app_start_measurements.csv"
        printf '%s\n' \
            'track,scenario,iteration,launch_state,total_time_ms,wait_time_ms,success,outcome' \
            >"$startup_file"
        for warmup in 1 2 3; do
            measure_launch_pair "$warmup" false "$startup_file"
        done
        for iteration in $(seq 1 20); do
            measure_launch_pair "$iteration" true "$startup_file"
        done

        if [[ "$block_number" -eq 1 ]]; then
            run_instrumentation \
                'com.mneme.app.ui.graph.GraphScreenTest,com.mneme.app.ui.MnemeAppFlowTest' \
                "$run_dir/instrumentation_functional.txt" \
                11
        fi
        run_instrumentation \
            'com.mneme.app.evaluation.E4StateMeasurementTest,com.mneme.app.evaluation.E4EventSyncMeasurementTest,com.mneme.app.ui.graph.E4GraphMeasurementTest' \
            "$run_dir/instrumentation_measurement.txt" \
            4

        "$ADB" -s "$current_serial" pull \
            /sdcard/Android/data/com.mneme.app/files/e4-evaluation/. \
            "$run_dir/" \
            >/dev/null

        jq -n \
            --arg schema_version "android-factorial-completion-v1" \
            --arg completed_at_utc "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
            --argjson expected_controlled_samples 810 \
            --argjson measurement_tests 4 \
            --argjson functional_tests "$([[ "$block_number" -eq 1 ]] && printf 11 || printf 0)" \
            '{
                schema_version: $schema_version,
                completed_at_utc: $completed_at_utc,
                expected_controlled_samples: $expected_controlled_samples,
                measurement_tests: $measurement_tests,
                functional_tests: $functional_tests
            }' \
            >"$run_dir/completed.json"

        "$ADB" -s "$current_serial" shell am force-stop com.mneme.app
        stop_emulator
        printf 'Completed block %s/4 position %s/4: %s\n' \
            "$block_number" "$position" "$config_id"
    done
done

printf 'Android CPU x RAM factorial raw artifacts written to %s\n' "$RAW_ROOT"
