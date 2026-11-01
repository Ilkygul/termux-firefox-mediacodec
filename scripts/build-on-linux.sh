#!/usr/bin/env bash
# External build host only. Never installs or changes the phone's browser.
set -euo pipefail
stage="${1:-baseline}"
work="${2:-$PWD/fold-firefox-build}"
jobs="${FOLD_FIREFOX_BUILD_JOBS:-2}"
[[ "$jobs" =~ ^[1-9][0-9]*$ ]] || { echo 'FOLD_FIREFOX_BUILD_JOBS must be a positive integer.' >&2; exit 2; }
case "$stage" in baseline|patched) ;; *) echo 'Usage: build-on-linux.sh baseline|patched [build-directory]' >&2; exit 2;; esac
if [[ "$(uname -s)" != Linux || "$(uname -m)" != x86_64 ]]; then
 echo 'Use a Linux x86_64 build host for the official Termux cross-toolchain.' >&2; exit 2
fi
command -v docker >/dev/null
command -v git >/dev/null
docker info >/dev/null
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
revision=9020eb6f9c26103fe7c67a6675a0303dc7adaa99
if [[ ! -e "$work" ]]; then
 git clone --depth=1 --filter=blob:none --no-checkout https://github.com/termux/termux-packages.git "$work"
 git -C "$work" fetch --depth=1 origin "$revision"
 git -C "$work" checkout --detach "$revision"
fi
work="$(cd -- "$work" && pwd -P)"
[[ "$(git -C "$work" rev-parse HEAD)" == "$revision" ]] || { echo 'Build checkout revision differs; inspect it manually.' >&2; exit 2; }
if [[ "$stage" == baseline ]]; then
 [[ -z "$(git -C "$work" status --porcelain)" ]] || { echo 'Baseline checkout is modified.' >&2; exit 2; }
else
 for patch in 1001-system-ffmpeg-preference.patch 1002-native-mediacodec-prototype.patch 1003-native-decoder-output-diagnostics.patch 1004-neon-interleaved-chroma.patch; do
  target="$work/x11-packages/firefox/$patch"
  [[ ! -e "$target" ]] || cmp -- "$source_dir/../patches/firefox/$patch" "$target"
  cp -- "$source_dir/../patches/firefox/$patch" "$target"
 done
fi
# Match build-host optimization settings in both stages; only patched gets
# runtime feature patches and the layout regression check.
cp -- "$source_dir/../patches/native-host/native-host-rust-thin-lto.patch" "$work/x11-packages/firefox/1000-build-host-thin-lto.patch"
if [[ "$stage" == patched ]]; then
 cp -- "$source_dir/check_plane_layout.py" "$work/x11-packages/firefox/fold-check-plane-layout.py"
 python3 - "$work/x11-packages/firefox/build.sh" <<'PATCH_RECIPE'
from pathlib import Path
import sys
p=Path(sys.argv[1]);text=p.read_text()
needle='termux_step_make() {\n'
assert needle in text
text=text.replace(needle,needle+'\tpython3 "$TERMUX_PKG_BUILDER_DIR/fold-check-plane-layout.py" --source "$TERMUX_PKG_SRCDIR"\n',1)
p.write_text(text)
PATCH_RECIPE
fi
container_name="${FOLD_FIREFOX_BUILD_CONTAINER:-fold-firefox-builder}"
image=ghcr.io/termux/package-builder@sha256:44999857244619e25bc8e3427904a16d36cc0c0e087704af039e5bdf94814ac9
if docker container inspect "$container_name" >/dev/null 2>&1; then
 existing_image="$(docker container inspect --format '{{.Config.Image}}' "$container_name")"
 existing_source="$(docker container inspect --format '{{range .Mounts}}{{if eq .Destination "/home/builder/termux-packages"}}{{.Source}}{{end}}{{end}}' "$container_name")"
 [[ "$existing_image" == "$image" && "$existing_source" == "$work" ]] || {
  echo 'Existing build container uses a different source directory or image; select a fresh name with FOLD_FIREFOX_BUILD_CONTAINER.' >&2
  exit 2
 }
fi
(
 cd -- "$work"
 export CONTAINER_NAME="$container_name"
 export TERMUX_BUILDER_IMAGE_NAME=ghcr.io/termux/package-builder@sha256:44999857244619e25bc8e3427904a16d36cc0c0e087704af039e5bdf94814ac9
 extra=()
 [[ "$stage" != patched ]] || extra=(-f)
 if [[ "$stage" == patched ]]; then
  ./scripts/run-docker.sh bash -lc 'export FOLD_NATIVE_RUST_LTO=thin CARGO_BUILD_JOBS="$1"; ./build-package.sh "-j$1" -a aarch64 -I -f firefox' fold-firefox-build "$jobs"
 else
  ./scripts/run-docker.sh bash -lc 'export FOLD_NATIVE_RUST_LTO=thin CARGO_BUILD_JOBS="$1"; ./build-package.sh "-j$1" -a aarch64 -I firefox' fold-firefox-build "$jobs"
 fi
)
mkdir -p -- "$work/output/fold-build-evidence"
docker image inspect ghcr.io/termux/package-builder@sha256:44999857244619e25bc8e3427904a16d36cc0c0e087704af039e5bdf94814ac9 > "$work/output/fold-build-evidence/builder-image.json"
git -C "$work" rev-parse HEAD > "$work/output/fold-build-evidence/termux-revision.txt"
printf '%s\n' "$stage" > "$work/output/fold-build-evidence/stage.txt"
printf '%s\n' "$jobs" > "$work/output/fold-build-evidence/jobs.txt"
echo 'Build finished. Packages are in the official Termux output directory; they are not installed on the phone.'
