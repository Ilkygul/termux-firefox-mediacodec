# Firefox 159 maintenance result

Firefox 159.0-0+fold1 and FFmpeg 9.0.2-1 are installed together as native
Android/Bionic packages. The [cross-build](https://github.com/Ilkygul/termux-firefox-mediacodec/actions/runs/41340203512)
succeeded. The package payload and installed library hashes match the tested
artifacts; package audits and dependency checks pass. The existing user profile
and signed active Bitwarden extension were preserved.

## Runtime correction

The device's libandroid-stub 30-3 Binder forwarder lacks a SONAME and five Binder
exports required by its Android vendor allocator. This caused an RDD crash and
software fallback despite successful codec initialization. A browser-private
forwarder adds the SONAME and forwards the missing parcel, stability and class
functions through Termux's existing shared platform namespace. Its source pins
and patch are in `runtime-pins.json`. The global Android/Termux libraries remain
package-managed. The Firefox launcher selects the private forwarder.

To build this small runtime component in native Termux:

```sh
python scripts/prepare_binder_runtime.py --output .work/runtime-lib/libbinder_ndk.so
```

Stage that file at `$PREFIX/lib/firefox/native-system/libbinder_ndk.so`, retain the
upstream NCSA copyright, and package `examples/firefox-launcher.sh` as
`$PREFIX/bin/firefox`. These are staging instructions, not permission to overwrite
an installed approved package. Include `libandroid-stub (>= 30-3)` as a dependency.
Keep the actual native Firefox ELF at `$PREFIX/lib/firefox/firefox`.

## Short validation selected for this maintenance

The user limited browser testing to two minutes. Four functional cases passed:

| Case | Observed result |
| --- | --- |
| H.264 | Hardware output from c2.qti.avc.decoder; rendered frames |
| VP9 | Hardware output from c2.qti.vp9.decoder; rendered frames |
| AV1 fallback | Software output; rendered frames |
| Hardware disabled | Software output with the global hardware preference off |

Native execution was untraced, the expected libxul and staged FFmpeg 9 were
loaded, and passed browser trials exited cleanly. The final hardware-disable
sample was 800 ms and included seek and pause/resume checks. Earlier failed
attempts count toward the same budget. The conservative charged total was
118.10 seconds. No further browser trials were run after that budgeted check.

This is not the full 14-case matrix, a 4K/10-bit/streaming qualification, a long
stability test or a new performance/battery benchmark. Historical Firefox 158
measurements are retained separately.

Run the bounded check with the actual ELF and a directory containing the staged
FFmpeg libraries. The runner selects the Binder bridge beside the Firefox ELF:

```sh
python scripts/validate_smoke.py --binary /absolute/stage/lib/firefox/firefox \
  --codec-dir /absolute/stage/lib --work .work/smoke
```

The explicit approval route is:

```sh
fold-firefox-maintenance approve candidate.deb --validation summary.json \
  --allow-maintenance-smoke --codec-package ffmpeg.deb
```

It requires all four cases, an enforced time budget, actual hardware output,
software fallback, native execution and exact browser/codec payload hashes.
The approved launcher and private Binder runtime hashes are also checked.
The default approval route still requires the full matrix. Ordinary general
updates no longer need the temporary FFmpeg-version pin, because the installed
browser supports the current FFmpeg ABI.

References: [Termux runtime sources](https://github.com/termux/termux-packages/tree/18e1ade601f424b7b2690607c50f5ca1fc6de0de/packages/libandroid-stub),
[Android Binder shell declarations](https://android.googlesource.com/platform/frameworks/native/+/master/libs/binder/ndk/include_platform/android/binder_shell.h).
