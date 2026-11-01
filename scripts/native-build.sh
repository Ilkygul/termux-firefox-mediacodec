#!/data/data/com.termux/files/usr/bin/bash
# SPDX-License-Identifier: MPL-2.0
# Native Termux only. Retain completed objects; never install a browser.
set -u
runner_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
jobs="${1:-6}"
case "$jobs" in [1-8]) ;; *) echo 'Usage: native-build.sh [jobs: 1-8]' >&2; exit 2;; esac
while :; do
 if python "$runner_dir/native-stage.py" build --jobs "$jobs" --full-power; then
  exit 0
 else
  status=$?
 fi
 # Only the controller's explicit memory-pressure exit requests a retry.
 if [[ "$status" != 75 || "$jobs" == 1 ]]; then
  exit "$status"
 fi
 if (( jobs > 4 )); then jobs=4; elif (( jobs > 2 )); then jobs=2; else jobs=1; fi
 echo "Memory pressure: resuming completed build objects with $jobs job(s)." >&2
done
