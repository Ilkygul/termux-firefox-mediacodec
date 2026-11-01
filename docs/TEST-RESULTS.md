# Test results and provenance

## Firefox 159 deployed maintenance status

Firefox 159.0-0+fold1 and FFmpeg 9.0.2-1 are installed. A bounded four-case
maintenance smoke check passed, including actual H.264/VP9 hardware output,
AV1 software fallback and the hardware-disable preference. The charged total,
including earlier failed attempts, was 118.10 seconds. See
[the maintenance result](MAINTENANCE-159.md) for scope, the Binder runtime fix,
source provenance and deployment checks. All complete-matrix and performance
results below are historical Firefox 158 results.

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
