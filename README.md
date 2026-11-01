> Candidate branch: Firefox 159.0 / FFmpeg 9 source port. The phone still uses the
> validated Firefox 158 build. Candidate code/configure checks are not hardware
> playback certification; no candidate browser has been approved or installed.

# Native Firefox MediaCodec for Termux

H.264 and VP9 hardware video decoding in the **native GTK/X11 Termux build of Firefox**, through system FFmpeg and Android's MediaCodec NDK API. The browser runs directly on Android/Bionic: no PRoot browser, codec proxy, extra decoding daemon, or emulated desktop architecture.

This is a community source patchset and maintenance workflow, **not an official Mozilla or Termux release**. It was developed and tested on one Qualcomm Android phone running Termux:X11/XFCE. Other devices and codecs need their own validation. The patches currently target Firefox **158.0**, not arbitrary future releases.

## What was implemented

- Opt-in priority for system FFmpeg, allowing VP9 to reach the native MediaCodec path instead of Firefox's bundled software decoder.
- Lazy Binder thread-pool initialization for Java-free MediaCodec/Codec2 operation.
- H.264/VP9 8-bit eligibility checks, initialization failure fallback, and respect for Firefox's global hardware-decoding disable setting.
- NV12 transfer through Firefox's image-copy paths, with ARM64 NEON chroma extraction and a scalar tail that avoids a V-plane overread.
- First-output diagnostics that distinguish real hardware-decoded frames from provisional decoder initialization.
- An APT update guard: unapproved Firefox packages are rejected before unpacking; incompatible FFmpeg ABI/codec markers are rejected as well.

Both feature preferences are **off in source by default**. Isolated test profiles enable them explicitly. Production opt-in examples are in [`examples/`](examples/).

## Evidence, not a universal performance promise

The original 14-case browser matrix passed. It covers H.264, 4K H.264, VP9, AV1 and 10-bit software fallback, H.264/AAC Media Source Extensions, seeks, pause/resume, concurrent decoding, resizing, frame-callback timing and repeated software/hardware comparisons. Actual output reported `MediaCodec NDK video decoder (system FFmpeg)` with `hw="true"`, alongside `c2.qti.avc.decoder` or `c2.qti.vp9.decoder`. Native execution was untraced and the expected `libxul.so` was loaded.

| Original repeated test | Mean software browser CPU | Mean hardware browser CPU | Relative reduction |
| --- | ---: | ---: | ---: |
| 4K H.264 | 100.17% of one core | 80.94% | 19.2% |
| 1080p VP9 | 73.20% of one core | 51.58% | 29.5% |

These are short test-media browser-process measurements. They exclude Android codec-service CPU/memory. Browser PSS did not consistently decrease. They do **not** establish battery savings or performance on every website. AV1 and 10-bit H.264 retain software fallback. Frame-callback samples are not proof of physical display presentation rate.

The final packaged browser also passed public HTTPS video, TLS verification, signed Bitwarden/uBlock Origin, a rendered Bitwarden popup, real-profile hardware decoding and native/Debian link handling checks. Automatic DPI settings were preserved; physical folding/DeX transitions and audible A/V sync were not measured. See [test results](docs/TEST-RESULTS.md) and [sanitized evidence](evidence/).

## Start here

1. Read the [architecture and limits](docs/ARCHITECTURE.md).
2. Follow the [build instructions](docs/BUILD.md). Build output is a **candidate**, not an approved release.
3. Stage and run the [on-device tests](docs/TESTING.md). CI cannot certify an Android hardware decoder.
4. Follow the [update-maintenance procedure](docs/UPDATES.md) before promoting a candidate.
5. Review the [executed implementation plan](docs/EXECUTED-PLAN.md).

For host-side guard tests, no browser or Android device is needed:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/check_repository.py
```

## Keeping acceleration through updates

The guard approves **exact package bytes and tested browser binaries**, not a version string or a filename containing “hardware.” General environment updates can keep the current validated Firefox using a temporary, per-command APT preference. No persistent `apt-mark hold` is added. Direct APT attempts to install an unknown Firefox package fail before unpacking.

This protection is a maintenance obligation, not an endless security freeze: if a newer Firefox is available, the status command explicitly reports that a security update may be pending. Rebase, build, run the full matrix, approve the exact candidate, then install it. **An unported Firefox security update must not be silently ignored.** The upstream-monitor workflow signals recipe/release drift; it does not invent a tested replacement.

The guard covers APT transactions. Direct `dpkg`, manual file replacement, Android firmware changes and an intentional guard removal can bypass it. The FFmpeg precheck detects required ABI aliases and codec markers; it cannot prove that every same-ABI update behaves correctly at runtime. Run the video matrix after relevant codec/driver changes. No automatic rollback, profile backup or background service is installed.

## Scope and licensing

The build follows the native Termux GTK/X11 configuration, including its disabled Firefox sandbox. Do not assume it has the same isolation properties as Firefox for Android. The official Termux/Mozilla projects have not reviewed or endorsed this patchset.

No browser profile, vault, cookie store, SSH key, access token, downloaded extension package or prebuilt browser binary is published here. Generated clips and build artifacts stay under ignored `.work/` directories. Original source/configuration pins, small patches, test code and sanitized measurements are retained.

Repository contributions and Mozilla-derived changes are provided under [MPL-2.0](LICENSE), with upstream third-party notices preserved; see [NOTICE](NOTICE). Firefox, Termux and Bitwarden names remain their owners' trademarks. This repository does not grant branding rights for redistributed binaries.
