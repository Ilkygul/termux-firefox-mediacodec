# Test results and provenance

## Firefox 159 candidate status

The 159.0 source port is pinned in `sources.json`; it is not yet an installed or
runtime-approved browser. The 22 existing host checks pass. A new process-group
cleanup test also passes in native Termux and in [GitHub checks](https://github.com/Ilkygul/termux-firefox-mediacodec/actions/runs/41343612126).
The cleanup test deliberately skips PRoot tracing, where stop states differ.
It opens no browser.

The NV12 layout regression check compiles against the actual upstream plane
metadata, noncopyable owning subclass and CheckedInt declarations. It checks
valid and malformed shared-UV layouts; this is a C++ source check, not a claim
about FFmpeg ABI compatibility or real decoded frames. It caught the distinction
between copying `YCbCrBuffer` metadata and copying the owning `QuantizableBuffer`.

The [cross-build](https://github.com/Ilkygul/termux-firefox-mediacodec/actions/runs/41340203512)
and the native phone build are still in progress. FFmpeg 9.0.2-1 was downloaded
and statically inspected for ABI aliases and NDK decoder markers, but not installed.
No Firefox 159 browser playback trials have been run. All browser and performance
results in the remaining sections are historical Firefox 158 results.

The evidence files are sanitized exports of real development/deployment receipts. `publication.source_receipt_sha256` identifies each original private receipt; `evidence/index.json` fingerprints the public exports. Session payloads, raw log tails, profile paths and unrelated desktop hashes were removed. Paths are placeholders, not executable locations.

## Original native build and source validation

- Firefox: 158.0, local installed package `158.0-1+fold1`, AArch64 Android/Bionic.
- Official Termux recipe: `e2b25a170e34052eb30fdb64da0593bc69499ca9`.
- Native build 11: successful; four feature patches plus five host patches.
- Full patched matrix: all 14 cases passed, artifact fingerprints unchanged.
- Real hardware decoders: `c2.qti.avc.decoder` and `c2.qti.vp9.decoder`, with actual decoded-output hardware state, not initialization alone.
- ARM copy unit: 576 actual-function guard-page/byte-equality cases passed.

See `runtime-original.json`, `baseline-original.json`, `patch-composition.json`, `native-build.json` and `neon-copy.json`.

## Original repeated CPU/PSS samples

| Clip | Software browser CPU samples | Hardware browser CPU samples | Relative mean CPU reduction |
| --- | --- | --- | --- |
| 4K H.264 | 100.199%, 100.147% | 81.586%, 80.297% | 19.198% |
| 1080p VP9 | 72.601%, 73.808% | 50.044%, 53.116% | 29.540% |

Each value uses one CPU core as 100%. Browser PSS varied: no consistent memory reduction was established. Android codec services are outside this accounting. All four rows of each comparison counted zero dropped frames. Other clips, codec configurations, thermal conditions and sites can differ.

## Package and real-profile checks

- Independently reproduced symbol stripping matched the staged package's exact browser/library hashes.
- Packaged H.264 4K, VP9 and HTTPS H.264/AAC playback passed.
- TLS checks kept certificate validation enabled.
- Bitwarden 2026.10.0 and uBlock Origin 1.75.0 were signed and active; Bitwarden rendered its popup and was pinned.
- Native and Debian default links reached the same untraced native browser.
- A final real-profile trial produced hardware H.264 frames with the installed `libxul.so` and exited cleanly.
- Installed package audit/checksums passed; build residue and temporary access were removed.

See `package-strip-proof.json`, `package-runtime.json`, `desktop-smoke.json`, `normal-profile-hardware.json` and `environment-audit.json`.

## Update protection

Host unit tests exercise package/version/payload rejection, complete native validation requirements and temporary-pin cleanup. Synthetic test fixtures are not evidence of video playback.

The native APT integration test passed three cases against an isolated status file and refusing dpkg stub. Unknown Firefox and incompatible FFmpeg were stopped before dpkg unpacking. An unrelated package reached the refusing stub. The live dpkg status hash remained unchanged. The integrated general-update simulation retained the approved Firefox and did not install any real package.

See `update-guard-native-apt.json` and `update-guard-install.json`.

## Public harness rerun

The portable runtime runner and fixture generator were reorganized for this repository after deployment. Its optional fresh on-device run was intentionally stopped; it is not reported as a second full matrix pass. Completed cases are recorded in `public-harness-interrupted.json`. The original fully passed matrix remains the deployment evidence. Regenerated clips are new encoded files, so their timing samples must not be substituted for the original comparison table without reporting that change.
