#!/bin/bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PACKAGE_NAME="com.mneme.app"
TRIGGER_ACTION="com.mneme.app.debug.action.TRIGGER_DIGEST_SYNC"
TRIGGER_COMPONENT="com.mneme.app/.debug.DigestSyncDemoReceiver"
BACKEND_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
RUN_DIR=${MNEME_DEMO_RUN_DIR:-/tmp/mneme-mvp-demo}
ADB=${ADB:-${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Android/Sdk}}/platform-tools/adb}

fail() {
  echo "Error: $*" >&2
  exit 1
}

is_checkout_api_process() {
  local pid=$1 command
  [ -r "/proc/$pid/cmdline" ] || return 1
  command=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
  case "$command" in
    *"$BACKEND_PYTHON -m uvicorn mneme.main:app"*) return 0 ;;
    *) return 1 ;;
  esac
}

[ -x "$BACKEND_PYTHON" ] || fail "Backend environment is missing. Run 'cd backend && uv sync --locked --dev'."
[ -x "$ADB" ] || fail "adb was not found. Set ANDROID_HOME or ADB."

if [ -n "${ANDROID_SERIAL:-}" ]; then
  SERIAL=$ANDROID_SERIAL
else
  mapfile -t EMULATORS < <("$ADB" devices | awk '$1 ~ /^emulator-/ && $2 == "device" {print $1}')
  [ "${#EMULATORS[@]}" -eq 1 ] || fail \
    "Exactly one Android emulator is required. Set ANDROID_SERIAL when more than one is running."
  SERIAL=${EMULATORS[0]}
fi
ADB_DEVICE=("$ADB" -s "$SERIAL")
"${ADB_DEVICE[@]}" get-state >/dev/null 2>&1 || fail "The selected Android emulator is unavailable."
"${ADB_DEVICE[@]}" shell pm path "$PACKAGE_NAME" >/dev/null 2>&1 || fail "The Mneme debug app is not installed."
"${ADB_DEVICE[@]}" shell dumpsys package "$PACKAGE_NAME" \
  | grep -Fq "$TRIGGER_ACTION" \
  || fail "The installed APK does not contain the local debug notification trigger. Run ./tools/start_local_mvp_demo.sh first."

API_PID=${MNEME_API_PID:-}
if [ -z "$API_PID" ]; then
  if [ -s "$RUN_DIR/api.pid" ] \
      && kill -0 "$(cat "$RUN_DIR/api.pid")" 2>/dev/null \
      && is_checkout_api_process "$(cat "$RUN_DIR/api.pid")"; then
    API_PID=$(cat "$RUN_DIR/api.pid")
  else
    API_PID=$(pgrep -f "$BACKEND_PYTHON -m uvicorn mneme.main:app" | head -n 1 || true)
  fi
fi
[ -n "$API_PID" ] || fail "The local Mneme API is not running."
[[ $API_PID =~ ^[0-9]+$ ]] || fail "MNEME_API_PID must be a numeric process ID."
is_checkout_api_process "$API_PID" || fail "The selected API process is not from this checkout."
[ -r "/proc/$API_PID/environ" ] || fail "The local API environment cannot be read."

# Reuse only the non-provider settings needed by the existing recommender.
while IFS= read -r -d '' item; do
  name=${item%%=*}
  case "$name" in
    MNEME_DATABASE_URL | MNEME_DEMO_USER_ID | MNEME_DATABASE_POOL_SIZE | \
      MNEME_DATABASE_MAX_OVERFLOW | MNEME_DATABASE_POOL_TIMEOUT_SECONDS | \
      MNEME_DATABASE_POOL_RECYCLE_SECONDS | MNEME_AI_RECOMMENDATION_CANDIDATE_DAYS | \
      MNEME_AI_RECOMMENDATION_MAX_ENTRIES | MNEME_DIGEST_NOTIFICATION_THRESHOLD)
      export "$item"
      ;;
  esac
done < "/proc/$API_PID/environ"
NOTIFICATION_THRESHOLD=${MNEME_DIGEST_NOTIFICATION_THRESHOLD:-0.75}

echo "Generating a weekly briefing from the current seed, interests, and behavior..."
WEEKLY_RESULT=$(
  cd "$ROOT_DIR/backend"
  "$BACKEND_PYTHON" -m mneme.cli.prepare_demo_weekly
) || fail "Weekly briefing generation failed. Complete seed onboarding before running this script."
WEEKLY_JSON=$(printf '%s\n' "$WEEKLY_RESULT" | tail -n 1)

DIGEST_ID=$(
  "$BACKEND_PYTHON" -c 'import json,sys; print(json.loads(sys.stdin.read())["digest_id"])' \
    <<<"$WEEKLY_JSON"
)
ENTRY_COUNT=$(
  "$BACKEND_PYTHON" -c 'import json,sys; print(json.loads(sys.stdin.read())["entry_count"])' \
    <<<"$WEEKLY_JSON"
)
MAXIMUM_RELEVANCE=$(
  "$BACKEND_PYTHON" -c 'import json,sys; print(json.loads(sys.stdin.read())["maximum_relevance"])' \
    <<<"$WEEKLY_JSON"
)

echo "Weekly briefing ready: $ENTRY_COUNT papers; maximum relevance $MAXIMUM_RELEVANCE."
if [ "$ENTRY_COUNT" -le 0 ] || [ "$MAXIMUM_RELEVANCE" = "None" ]; then
  fail "The real weekly recommender produced no eligible paper, so no alert can be published."
fi
if ! "$BACKEND_PYTHON" -c \
    'import sys; raise SystemExit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)' \
    "$MAXIMUM_RELEVANCE" "$NOTIFICATION_THRESHOLD"; then
  fail "The weekly briefing did not meet the configured relevance threshold $NOTIFICATION_THRESHOLD."
fi

"${ADB_DEVICE[@]}" reverse tcp:8000 tcp:8000 >/dev/null

echo "Asking the existing Android worker to apply its notification threshold..."
"${ADB_DEVICE[@]}" shell am broadcast \
  -n "$TRIGGER_COMPONENT" \
  -a "$TRIGGER_ACTION" \
  >/dev/null

for _ in $(seq 1 30); do
  if "${ADB_DEVICE[@]}" shell "run-as $PACKAGE_NAME cat shared_prefs/digest_notifications.xml 2>/dev/null" \
      | grep -Fq "$DIGEST_ID" \
      && "${ADB_DEVICE[@]}" shell cmd notification list | grep -Fq "$PACKAGE_NAME"; then
    echo "Notification ready. Pull down the Android notification shade when you want to demonstrate it."
    exit 0
  fi
  sleep 1
done

fail "The original Android notification path did not publish this digest. Check notification permission, backend connectivity, and the configured relevance threshold."
