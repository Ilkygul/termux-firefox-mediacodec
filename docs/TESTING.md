# Tests and acceptance gates

## Host-side tests

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_repository.py
```

These test update-guard decisions, package integrity, approval requirements and temporary-pin cleanup. Synthetic packages/receipts in unit tests are explicitly test fixtures: they are **not** hardware playback evidence.

`tests/native_apt_integration.py` additionally exercises real native APT hooks against an isolated dpkg status file and a dpkg stub that refuses mutations. An unapproved Firefox and an incompatible FFmpeg must stop before that stub; an unrelated package must reach the refusing stub. The live dpkg status hash must remain unchanged. This is an APT integration test, not a real package upgrade.

## Native browser matrix

Use native Termux Python and FFmpeg, a working Termux:X11/XFCE session, and a candidate binary. PRoot/traced execution is refused.

```sh
python scripts/generate_fixtures.py
python scripts/validate_runtime.py --list
python scripts/validate_runtime.py --binary /absolute/path/to/staged/firefox
```

Fixture generation uses one encoding thread and low priority. It produces generated test patterns and a generated sine wave, not copyrighted film clips or recordings of the user's desktop. A manifest records commands, encoder version and file hashes. The original media files were intentionally deleted after deployment: regenerated fixtures are equivalent test scenarios, not a claim to recreate the historic encoded bytes or exact CPU samples.

Results live in `.work/runtime/validation-*/summary.json`, with per-case stdout/stderr. The executable and `libxul.so` are fingerprinted before and after the matrix. The browser opens disposable test windows; the runner does not copy or use the normal Firefox profile. It verifies native untraced execution, expected loaded `libxul`, actual MediaCodec output, codec startup, frame counts, error state, seeks, pause/resume and clean shutdown.

| Case | Required behavior |
| --- | --- |
| H.264 / 4K H.264 / VP9 | Compare software with real Qualcomm hardware decoding |
| AV1 / 10-bit H.264 | Software fallback in both trial modes |
| H.264 High + AAC through MSE | Video playback and an audio track present |
| H.264 / VP9 selection diagnostics | Actual decoded output, not only initialization text |
| Global hardware disable | Software even with the feature preferences enabled |
| Two videos + three window sizes | Continuous playback, no counted drops, remaining video continues |
| 4K / VP9 pacing | Nonempty `requestVideoFrameCallback` interval samples |
| 4K / VP9 ABBA | Software, hardware, hardware, software repeated comparisons |

The probe currently recognizes Qualcomm `c2.qti.*` codec names. A different vendor may need an explicit, reviewed extension to the codec-evidence recognizer; do not remove the actual-output requirement simply to make a test pass.

A `complete=true` receipt requires all 14 cases and unchanged artifacts. It does not by itself prove lower CPU, total-phone memory savings, battery savings, audible A/V synchronization, every streaming site, DRM/Widevine support or physical monitor transitions.

## ARM64 copy correctness

`tests/neon-copy-test.cpp` contains the actual original and optimized copy functions used during development, with small type shims. It tests 576 width/height/skip/element-size/padding combinations, right-aligns sources against `PROT_NONE` guard pages, compares all output bytes including padding/canaries, and then prints an isolated microbenchmark.

Build/run on native ARM64 Termux:

```sh
clang++ --target=aarch64-linux-android24 -O2 -D__TERMUX__=1 -U__ANDROID__ -D_LIBCPP_HAS_NO_C11_ALIGNED_ALLOC tests/neon-copy-test.cpp -o .work/neon-copy-test
.work/neon-copy-test
```

The microbenchmark is not a browser CPU result. The scalar tail intentionally avoids a full interleaved load at the final V-plane sample.

## Daily-use checks before promotion

In addition to the matrix, verify HTTPS with certificate validation enabled, signed/active extensions, an actually rendered Bitwarden popup, default links reaching the intended native browser, unsupported-stream fallback and the intended display/scaling setup. The original deployment has sanitized results for these checks in `evidence/`; it did not log in to Bitwarden or copy a vault.

If a cross-origin test video taints a canvas, use a same-origin test document or report that pixel reads are unavailable. Do not disable browser security or fabricate pixel checks. An earlier cross-origin test failure is documented in the executed plan.
