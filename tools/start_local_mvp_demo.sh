#!/bin/bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BACKEND_DIR="$ROOT_DIR/backend"
ANDROID_DIR="$ROOT_DIR/android"
RUN_DIR=${MNEME_DEMO_RUN_DIR:-/tmp/mneme-mvp-demo}
LOCAL_ENV_FILE=${MNEME_DEMO_ENV_FILE:-$BACKEND_DIR/.env.local}
DEFAULT_DATABASE_URL="postgresql+asyncpg:///mneme_mvp_current"
AVD_NAME=${MNEME_DEMO_AVD:-Mneme_Pixel_9_Pro_XL_API_34}
EMULATOR_MEMORY_MB=${MNEME_DEMO_EMULATOR_MEMORY_MB:-14336}
EMULATOR_CORES=${MNEME_DEMO_EMULATOR_CORES:-6}
ANDROID_SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}
export ANDROID_SDK_ROOT
export ANDROID_HOME=${ANDROID_HOME:-$ANDROID_SDK_ROOT}
ADB=${ADB:-$ANDROID_SDK_ROOT/platform-tools/adb}
EMULATOR=${EMULATOR:-$ANDROID_SDK_ROOT/emulator/emulator}
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"
ARQ="$BACKEND_DIR/.venv/bin/arq"
JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
STARTUP_COMPLETE=false
BACKEND_STARTED=false

fail() {
  echo "Error: $*" >&2
  exit 1
}

note() {
  echo "[Mneme demo] $*" >&2
}

cleanup_on_exit() {
  local pid_file pid
  if [ "$STARTUP_COMPLETE" = true ] || [ "$BACKEND_STARTED" != true ]; then
    return
  fi
  for pid_file in "$RUN_DIR/api.pid" "$RUN_DIR/worker.pid"; do
    if [ -s "$pid_file" ]; then
      pid=$(cat "$pid_file")
      kill "$pid" 2>/dev/null || true
    fi
  done
}

trap cleanup_on_exit EXIT INT TERM

is_checkout_api_process() {
  local pid=$1 command
  [ -r "/proc/$pid/cmdline" ] || return 1
  command=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
  case "$command" in
    *"$BACKEND_PYTHON -m uvicorn mneme.main:app"*) return 0 ;;
    *) return 1 ;;
  esac
}

load_running_api_environment() {
  local api_pid item name
  api_pid=""
  if [ -s "$RUN_DIR/api.pid" ] \
      && kill -0 "$(cat "$RUN_DIR/api.pid")" 2>/dev/null \
      && is_checkout_api_process "$(cat "$RUN_DIR/api.pid")"; then
    api_pid=$(cat "$RUN_DIR/api.pid")
  else
    api_pid=$(pgrep -f "$BACKEND_PYTHON -m uvicorn mneme.main:app" | head -n 1 || true)
  fi
  [ -n "$api_pid" ] || return 0
  [ -r "/proc/$api_pid/environ" ] || return 0
  while IFS= read -r -d '' item; do
    name=${item%%=*}
    case "$name" in
      MNEME_AI_DAILY_BUDGET_USD | MNEME_AI_EMBEDDING_BACKEND | \
        MNEME_AI_EMBEDDING_MODEL | MNEME_AI_LOCAL_EMBEDDING_MODEL | \
        MNEME_AI_RECOMMENDATION_CANDIDATE_DAYS | MNEME_AI_RECOMMENDATION_MAX_ENTRIES | \
        MNEME_DIGEST_NOTIFICATION_THRESHOLD | \
        MNEME_ARXIV_DAILY_CATEGORIES | MNEME_ARXIV_DAILY_MAX_RESULTS | \
        MNEME_DATABASE_URL | MNEME_DEBUG | MNEME_DEEPSEEK_API_KEY | \
        MNEME_DEEPSEEK_THINKING_ENABLED | MNEME_DEMO_USER_ID | MNEME_ENVIRONMENT | \
        MNEME_LLM_QA_MODEL | MNEME_LLM_SUMMARY_MODEL | MNEME_LOG_LEVEL | \
        MNEME_PAPER_STORAGE_DIR | MNEME_REDIS_URL | MNEME_SEMANTIC_SCHOLAR_API_KEY)
        if [ -z "${!name+x}" ]; then
          export "$item"
        fi
        ;;
    esac
  done < "/proc/$api_pid/environ"
}

load_local_environment() {
  if [ -f "$LOCAL_ENV_FILE" ]; then
    note "Loading ignored local provider configuration from $LOCAL_ENV_FILE"
    set -a
    # shellcheck disable=SC1090
    . "$LOCAL_ENV_FILE"
    set +a
  fi
}

require_provider_configuration() {
  if [ -z "${MNEME_DEEPSEEK_API_KEY:-}" ]; then
    if [ -t 0 ]; then
      read -r -s -p "DeepSeek API key: " MNEME_DEEPSEEK_API_KEY
      echo
      export MNEME_DEEPSEEK_API_KEY
    fi
  fi
  [ -n "${MNEME_DEEPSEEK_API_KEY:-}" ] || fail \
    "MNEME_DEEPSEEK_API_KEY is required. Put it in the ignored backend/.env.local file."
  if [ -z "${MNEME_SEMANTIC_SCHOLAR_API_KEY:-}" ]; then
    note "Semantic Scholar key is absent; the backend will use its rate-limited public access."
  fi
}

is_local_service_host() {
  case "$1" in
    "" | localhost | 127.0.0.1 | ::1 | /*) return 0 ;;
    *) return 1 ;;
  esac
}

validate_demo_target() {
  [ "${MNEME_ENVIRONMENT,,}" != "production" ] \
    || fail "The local demo reset is disabled for a production environment."
  if ! is_local_service_host "$DATABASE_HOST" \
      && [ "${MNEME_ALLOW_REMOTE_DEMO_RESET:-false}" != "true" ]; then
    fail "The demo database is not local. Set MNEME_ALLOW_REMOTE_DEMO_RESET=true only for an isolated disposable demo database."
  fi
}

ensure_service() {
  local service=$1
  if ! systemctl is-active --quiet "$service"; then
    note "Starting $service (sudo may ask for your password)..."
    sudo systemctl start "$service"
  fi
}

redis_is_ready() {
  "$BACKEND_PYTHON" - <<'PY'
import asyncio
import os

from redis.asyncio import Redis


async def main() -> None:
    client = Redis.from_url(os.environ["MNEME_REDIS_URL"])
    try:
        await client.ping()
    finally:
        await client.aclose()


asyncio.run(main())
PY
}

stop_existing_backend() {
  local listener command pid
  listener=$(lsof -t -iTCP:8000 -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$listener" ]; then
    for pid in $listener; do
      command=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
      case "$command" in
        *"$BACKEND_DIR/.venv/bin/"*uvicorn*)
          note "Stopping the previous local API from this checkout."
          kill "$pid" 2>/dev/null || true
          ;;
        *) fail "Port 8000 is owned by another process: $pid" ;;
      esac
    done
  fi
  while IFS= read -r pid; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done < <(pgrep -f "$BACKEND_DIR/.venv/bin/arq mneme.tasks.worker.WorkerSettings" || true)
  for _ in $(seq 1 20); do
    if ! lsof -t -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1 \
        && ! pgrep -f "$BACKEND_DIR/.venv/bin/arq mneme.tasks.worker.WorkerSettings" >/dev/null; then
      return 0
    fi
    sleep 0.25
  done
  fail "The previous backend processes did not stop cleanly."
}

start_backend() {
  mkdir -p "$RUN_DIR"
  rm -f "$RUN_DIR/api.pid" "$RUN_DIR/worker.pid"
  note "Starting FastAPI and the ARQ worker."
  (
    cd "$BACKEND_DIR"
    setsid "$BACKEND_PYTHON" -m uvicorn mneme.main:app --host 127.0.0.1 --port 8000 \
      >"$RUN_DIR/api.log" 2>&1 </dev/null &
    echo $! >"$RUN_DIR/api.pid"
    setsid "$ARQ" mneme.tasks.worker.WorkerSettings \
      >"$RUN_DIR/worker.log" 2>&1 </dev/null &
    echo $! >"$RUN_DIR/worker.pid"
  )
  BACKEND_STARTED=true

  for _ in $(seq 1 60); do
    if [ -s "$RUN_DIR/api.pid" ] \
        && [ -s "$RUN_DIR/worker.pid" ] \
        && kill -0 "$(cat "$RUN_DIR/api.pid")" 2>/dev/null \
        && kill -0 "$(cat "$RUN_DIR/worker.pid")" 2>/dev/null \
        && curl --fail --silent http://127.0.0.1:8000/v1/health/ready >/dev/null; then
      return 0
    fi
    sleep 1
  done
  tail -n 30 "$RUN_DIR/api.log" >&2 || true
  fail "The local API did not become healthy."
}

running_emulator_serial() {
  local devices
  devices=$("$ADB" devices | awk '$1 ~ /^emulator-/ && $2 == "device" {print $1}')
  if [ "$(printf '%s\n' "$devices" | sed '/^$/d' | wc -l)" -gt 1 ]; then
    fail "More than one emulator is running. Stop extras or set up the demo with only one emulator."
  fi
  printf '%s\n' "$devices" | sed '/^$/d' | head -n 1
}

wait_for_emulator() {
  local serial=""
  for _ in $(seq 1 180); do
    serial=$(running_emulator_serial)
    if [ -n "$serial" ] \
        && [ "$("$ADB" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = "1" ]; then
      echo "$serial"
      return 0
    fi
    sleep 1
  done
  return 1
}

start_or_upgrade_emulator() {
  local serial memory_kb cpu_count required_kb
  serial=$(running_emulator_serial)
  required_kb=$((EMULATOR_MEMORY_MB * 1024 - 524288))
  if [ -n "$serial" ]; then
    if [ "$("$ADB" -s "$serial" shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" != "1" ]; then
      note "Waiting for the running emulator to finish booting."
      serial=$(wait_for_emulator) || fail "The running Android emulator did not finish booting."
    fi
    memory_kb=$("$ADB" -s "$serial" shell cat /proc/meminfo | awk '/MemTotal/ {print $2}')
    cpu_count=$("$ADB" -s "$serial" shell nproc | tr -d '\r')
    if [ "${memory_kb:-0}" -lt "$required_kb" ] || [ "${cpu_count:-0}" -lt "$EMULATOR_CORES" ]; then
      note "Restarting the emulator with ${EMULATOR_MEMORY_MB} MB RAM and $EMULATOR_CORES CPU cores."
      "$ADB" -s "$serial" emu kill >/dev/null || true
      for _ in $(seq 1 60); do
        [ -z "$(running_emulator_serial)" ] && break
        sleep 1
      done
      serial=""
    fi
  fi

  if [ -z "$serial" ]; then
    "$EMULATOR" -list-avds | grep -Fxq "$AVD_NAME" || fail "Android AVD '$AVD_NAME' was not found."
    note "Booting $AVD_NAME with ${EMULATOR_MEMORY_MB} MB RAM and $EMULATOR_CORES CPU cores."
    mkdir -p "$RUN_DIR"
    setsid "$EMULATOR" \
      -avd "$AVD_NAME" \
      -memory "$EMULATOR_MEMORY_MB" \
      -cores "$EMULATOR_CORES" \
      -gpu host \
      -feature -Vulkan \
      -no-snapshot \
      -no-boot-anim \
      -no-audio \
      >"$RUN_DIR/emulator.log" 2>&1 </dev/null &
    echo $! >"$RUN_DIR/emulator.pid"
    serial=$(wait_for_emulator) || {
      tail -n 40 "$RUN_DIR/emulator.log" >&2 || true
      fail "The Android emulator did not finish booting."
    }
  fi
  echo "$serial"
}

configure_emulator() {
  local serial=$1 memory_kb cpu_count required_kb
  "$ADB" -s "$serial" shell wm size 1080x2400 >/dev/null
  "$ADB" -s "$serial" shell wm density 420 >/dev/null
  "$ADB" -s "$serial" shell settings put global window_animation_scale 0
  "$ADB" -s "$serial" shell settings put global transition_animation_scale 0
  "$ADB" -s "$serial" shell settings put global animator_duration_scale 0
  memory_kb=$("$ADB" -s "$serial" shell cat /proc/meminfo | awk '/MemTotal/ {print $2}')
  cpu_count=$("$ADB" -s "$serial" shell nproc | tr -d '\r')
  required_kb=$((EMULATOR_MEMORY_MB * 1024 - 524288))
  [ "${memory_kb:-0}" -ge "$required_kb" ] \
    || fail "The emulator has less RAM than the requested ${EMULATOR_MEMORY_MB} MB."
  [ "${cpu_count:-0}" -ge "$EMULATOR_CORES" ] \
    || fail "The emulator has fewer CPU cores than the requested $EMULATOR_CORES."
  note "Emulator active: $cpu_count cores, $(awk -v kb="$memory_kb" 'BEGIN {printf "%.1f GB", kb/1024/1024}')."
}

validate_android_build_config() {
  MNEME_EXPECTED_DEMO_TOKEN="$MNEME_DEMO_TOKEN" \
  MNEME_EXPECTED_NOTIFICATION_THRESHOLD="$MNEME_DIGEST_NOTIFICATION_THRESHOLD" \
  MNEME_BUILD_CONFIG_FILE="$ANDROID_DIR/app/build/generated/source/buildConfig/debug/com/mneme/app/BuildConfig.java" \
    "$BACKEND_PYTHON" - <<'PY'
import json
import os
import re
from pathlib import Path

source = Path(os.environ["MNEME_BUILD_CONFIG_FILE"]).read_text(encoding="utf-8")


def string_value(name: str) -> str:
    match = re.search(rf"public static final String {name} = (\".*\");", source)
    if match is None:
        raise SystemExit("The generated Android configuration is incomplete.")
    return str(json.loads(match.group(1)))


def literal_value(name: str) -> str:
    match = re.search(rf"public static final (?:boolean|double) {name} = ([^;]+);", source)
    if match is None:
        raise SystemExit("The generated Android configuration is incomplete.")
    return match.group(1).strip()


matches = (
    string_value("MNEME_API_BASE_URL") == "http://127.0.0.1:8000/v1/"
    and string_value("MNEME_DEMO_TOKEN") == os.environ["MNEME_EXPECTED_DEMO_TOKEN"]
    and literal_value("MNEME_ALLOW_CONTROLLED_FIXTURE") == "false"
    and float(literal_value("MNEME_DIGEST_NOTIFICATION_THRESHOLD"))
    == float(os.environ["MNEME_EXPECTED_NOTIFICATION_THRESHOLD"])
)
if not matches:
    raise SystemExit(
        "The Android build did not use the live demo configuration. "
        "Remove conflicting Gradle project properties and retry."
    )
PY
}

install_and_open_android() {
  local serial=$1 sdk
  note "Building and installing the live Android debug app."
  export JAVA_HOME
  export MNEME_API_BASE_URL="http://127.0.0.1:8000/v1/"
  export MNEME_ALLOW_CONTROLLED_FIXTURE=false
  (
    cd "$ANDROID_DIR"
    export MNEME_DEMO_TOKEN
    ./gradlew --no-daemon :app:assembleDebug
  )
  validate_android_build_config
  "$ADB" -s "$serial" install -r "$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk" \
    >/dev/null

  "$ADB" -s "$serial" shell pm clear com.mneme.app >/dev/null
  sdk=$("$ADB" -s "$serial" shell getprop ro.build.version.sdk | tr -d '\r')
  if [ "${sdk:-0}" -ge 33 ]; then
    "$ADB" -s "$serial" shell pm grant \
      com.mneme.app android.permission.POST_NOTIFICATIONS
  fi
  "$ADB" -s "$serial" reverse tcp:8000 tcp:8000 >/dev/null
  "$ADB" -s "$serial" shell am start -n com.mneme.app/.MainActivity >/dev/null

  for _ in $(seq 1 30); do
    "$ADB" -s "$serial" shell rm -f /sdcard/mneme-demo-start.xml
    if "$ADB" -s "$serial" shell uiautomator dump /sdcard/mneme-demo-start.xml \
        >/dev/null 2>&1 \
        && "$ADB" -s "$serial" shell cat /sdcard/mneme-demo-start.xml \
        | grep -Fq "Start with one arXiv paper"; then
      if "$ADB" -s "$serial" shell cmd notification list | grep -Fq com.mneme.app; then
        fail "A stale Mneme notification remained after the clean reset."
      fi
      return 0
    fi
    sleep 1
  done
  fail "The app did not reach the seed onboarding screen."
}

command -v curl >/dev/null || fail "curl is required."
command -v lsof >/dev/null || fail "lsof is required."
command -v pgrep >/dev/null || fail "pgrep is required."
command -v pg_isready >/dev/null || fail "pg_isready is required."
command -v setsid >/dev/null || fail "setsid is required."
[ -x "$ADB" ] || fail "adb was not found at $ADB."
[ -x "$EMULATOR" ] || fail "The Android emulator was not found at $EMULATOR."
[ -x "$BACKEND_PYTHON" ] || fail "Backend dependencies are missing. Run 'cd backend && uv sync --locked --dev --extra local-embeddings'."
[ -x "$ARQ" ] || fail "The ARQ executable is missing from backend/.venv."
[ -x "$JAVA_HOME/bin/javac" ] || fail "JDK 17 was not found at $JAVA_HOME."

load_running_api_environment
load_local_environment
require_provider_configuration

export MNEME_DATABASE_URL=${MNEME_DATABASE_URL:-$DEFAULT_DATABASE_URL}
export MNEME_REDIS_URL=${MNEME_REDIS_URL:-redis://localhost:6379/0}
export MNEME_DEMO_USER_ID=${MNEME_DEMO_USER_ID:-$("$BACKEND_PYTHON" -c 'import uuid; print(uuid.uuid4())')}
export MNEME_AI_EMBEDDING_BACKEND=${MNEME_AI_EMBEDDING_BACKEND:-fastembed}
export MNEME_AI_LOCAL_EMBEDDING_MODEL=${MNEME_AI_LOCAL_EMBEDDING_MODEL:-BAAI/bge-small-en-v1.5}
export MNEME_LLM_SUMMARY_MODEL=${MNEME_LLM_SUMMARY_MODEL:-deepseek-chat}
export MNEME_LLM_QA_MODEL=${MNEME_LLM_QA_MODEL:-deepseek-chat}
export MNEME_DEEPSEEK_THINKING_ENABLED=${MNEME_DEEPSEEK_THINKING_ENABLED:-false}
export MNEME_DIGEST_NOTIFICATION_THRESHOLD=${MNEME_DIGEST_NOTIFICATION_THRESHOLD:-0.75}
export MNEME_PAPER_STORAGE_DIR=${MNEME_PAPER_STORAGE_DIR:-$BACKEND_DIR/.data/papers}
export MNEME_ENVIRONMENT=${MNEME_ENVIRONMENT:-development}
export MNEME_LOG_LEVEL=${MNEME_LOG_LEVEL:-INFO}
export MNEME_DEBUG=${MNEME_DEBUG:-false}

DATABASE_HOST=$("$BACKEND_PYTHON" -c \
  'import os; from sqlalchemy.engine import make_url; print(make_url(os.environ["MNEME_DATABASE_URL"]).host or "")')
REDIS_HOST=$("$BACKEND_PYTHON" -c \
  'import os; from urllib.parse import urlsplit; print(urlsplit(os.environ["MNEME_REDIS_URL"]).hostname or "")')
validate_demo_target

if [ "$MNEME_AI_EMBEDDING_BACKEND" = "fastembed" ]; then
  "$BACKEND_PYTHON" -c 'import fastembed' >/dev/null 2>&1 \
    || fail "Local embeddings are missing. Run 'cd backend && uv sync --locked --dev --extra local-embeddings'."
fi

MNEME_DEMO_TOKEN=$("$BACKEND_PYTHON" -c 'import secrets; print(secrets.token_urlsafe(32))')
export MNEME_DEMO_TOKEN_SHA256=$(
  printf '%s' "$MNEME_DEMO_TOKEN" \
    | "$BACKEND_PYTHON" -c 'import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())'
)

PG_READY_HOST=$DATABASE_HOST
PG_READY_PORT=$("$BACKEND_PYTHON" -c \
  'import os; from sqlalchemy.engine import make_url; print(make_url(os.environ["MNEME_DATABASE_URL"]).port or 5432)')
PG_READY_ARGS=()
[ -z "$PG_READY_HOST" ] || PG_READY_ARGS+=(--host "$PG_READY_HOST")
PG_READY_ARGS+=(--port "$PG_READY_PORT")
if is_local_service_host "$DATABASE_HOST"; then
  ensure_service postgresql
fi
pg_isready "${PG_READY_ARGS[@]}" >/dev/null 2>&1 \
  || fail "PostgreSQL is not ready after startup."
if [ "$MNEME_DATABASE_URL" = "$DEFAULT_DATABASE_URL" ]; then
  command -v psql >/dev/null || fail "psql is required for the default local database."
  command -v createdb >/dev/null || fail "createdb is required for the default local database."
  if ! psql --dbname postgres --tuples-only --no-align \
      --command "SELECT 1 FROM pg_database WHERE datname = 'mneme_mvp_current'" \
      | grep -Fxq 1; then
    note "Creating the default mneme_mvp_current database."
    createdb mneme_mvp_current
  fi
fi
if is_local_service_host "$REDIS_HOST"; then
  ensure_service redis-server
fi
redis_is_ready >/dev/null 2>&1 \
  || fail "Redis is not ready after startup."
stop_existing_backend

note "Applying database migrations and resetting the local demo identity."
(
  cd "$BACKEND_DIR"
  "$BACKEND_PYTHON" -m alembic upgrade head
  "$BACKEND_PYTHON" -m mneme.cli.bootstrap_demo_user >/dev/null
  "$BACKEND_PYTHON" -m mneme.cli.reset_demo_user >/dev/null
)

start_backend
printf 'header = "Authorization: Bearer %s"\nurl = "http://127.0.0.1:8000/v1/users/me/preferences"\n' \
  "$MNEME_DEMO_TOKEN" \
  | curl --fail --silent --config - >/dev/null \
  || fail "The generated Android token does not authenticate against the restarted API."
unset MNEME_ALLOW_REMOTE_DEMO_RESET MNEME_ANTHROPIC_API_KEY MNEME_DATABASE_URL MNEME_DEEPSEEK_API_KEY \
  MNEME_OPENAI_API_KEY MNEME_REDIS_URL MNEME_SEMANTIC_SCHOLAR_API_KEY
SERIAL=$(start_or_upgrade_emulator)
export ANDROID_SERIAL=$SERIAL
configure_emulator "$SERIAL"
install_and_open_android "$SERIAL"

STARTUP_COMPLETE=true
note "Ready. The API and worker logs are in $RUN_DIR."
note "The app is on the clean seed-paper screen with no prior interests, behavior, or notification."
note "After seed onboarding and interaction, run: ./tools/trigger_local_weekly_notification.sh"
