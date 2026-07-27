#!/usr/bin/env bash

set -euo pipefail

source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
figure_dir="$(dirname "$source_dir")"

render() {
  local name="$1"
  local width="$2"
  local height="$3"

  rsvg-convert \
    --width "$width" \
    --height "$height" \
    --output "$figure_dir/$name.png" \
    "$source_dir/$name.svg"
}

render chapter3_storymap 2400 1120
render chapter3_system_architecture 2400 1650
render chapter3_document_dag 2400 1450
render chapter3_behavior_loop 2400 900
render chapter3_ui_flow 2400 1550
