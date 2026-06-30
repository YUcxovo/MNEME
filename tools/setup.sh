#!/bin/bash
set -euo pipefail

check_cmd() {
  local cmd=$1
  local hint=$2
  if ! command -v "$cmd" &> /dev/null; then
    echo "$cmd is required but not detected. Please install it first. $hint"
    exit 1
  fi
}

echo "Setting up Mneme development environment..."
echo "Checking for required tools..."

check_cmd "git-lfs" "https://git-lfs.com/"
check_cmd "lefthook" "https://lefthook.dev/install/"

echo "Setting up backend dependencies..."
printf "Skip Backend dependencies setup? Only if you focus on Android development. [y/N] "
read -r REPLY < /dev/tty
case "$REPLY" in
    y|Y) ;;
    *) 
    check_cmd "uv" "https://docs.astral.sh/uv/getting-started/installation/"
    (cd backend && uv sync) 
    ;;
esac

echo "Setting up Android dependencies..."
printf "Skip Android dependencies setup? Only if you focus on backend development. [y/N] "
read -r REPLY < /dev/tty
case "$REPLY" in
    y|Y) ;;
    *) 
    check_cmd "ktlint" "https://ktlint.github.io/ktlint/latest/install/cli/#download-and-verification"
    if [ ! -f "android/local.properties" ]; then
        if [ -n "${ANDROID_HOME:-}" ]; then
            echo "sdk.dir=$ANDROID_HOME" > android/local.properties
        else
            echo "Please set ANDROID_HOME environment variable to your Android SDK path."
            exit 1
        fi
    fi
    ;;
esac

lefthook install
git config pull.rebase true
chmod +x tools/*.sh

echo ""
echo "Setup complete."