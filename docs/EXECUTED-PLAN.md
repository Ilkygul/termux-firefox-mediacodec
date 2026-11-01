# Executed implementation plan

The owner wanted one efficient native Linux-desktop browser on Android, working hardware video decoding, Bitwarden, useful environment defaults, flexible Fold/DeX scaling and no unnecessary backup/background load. The browser implementation was completed on 18 October 2026; update protection and this public repository were prepared afterward.

## 1. Inspect and compare the actual environment

Identified native Termux GTK/X11 Firefox, system FFmpeg and the distinction between native Android/Bionic applications and Debian/PRoot applications. Removed redundant Linux browser packages during the original environment work, preserving user data. Native Firefox became the single installed Linux browser; compatibility commands could redirect to it without constituting a second browser.

Pinned the Firefox 158.0 source, official Termux recipe revision, official patches and toolchain observations. A complete native baseline build and six-case software validation passed before feature patches were applied.

## 2. Prove access to Android's hardware decoder

Used small native decoder probes to establish real Qualcomm H.264/VP9 output and seek/flush behavior. Binder process initialization was necessary for Codec2 callbacks without a Java VM.

An experimental FFmpeg proxy proved H.264 decoding, including 4K. It did not make stock Firefox choose that path for VP9, because bundled FFVPX retained priority. The obsolete preference did not fix selection. That route was discarded as the deployment solution; no proxy library is installed.

## 3. Integrate the feature in Firefox source

Added explicit opt-in system-FFmpeg priority and MediaCodec enable preferences. Added eligible H.264/VP9 native decoder selection, Binder setup, hardware-disable checks, initialization fallback and NV12 image transfer through Firefox's existing copy paths.

Initialization logs could be provisional because Firefox creates some decoders lazily. Added first-actual-output diagnostics instead of claiming an initialization string proved hardware frames.

Verified the ordered patch composition on independently reconstructed baseline files. A preference-context collision between the first two patches was caught and corrected. A diagnostic initially tried to format an atomic boolean directly; an explicit boolean read fixed that compile error. Failed attempts remained separate from successful receipts.

## 4. Complete a constrained native build

Built natively on the phone. Host compatibility fixes addressed Rust host naming, Python's Android platform reporting, a private glslopt logging header and an API-24 pthread declaration mismatch. Full Rust LTO exhausted memory; ThinLTO succeeded. Both outer and inner make parallelism were checked, then restricted to two compiler jobs/two cores with low build priority.

The native baseline and patched builds both completed successfully. No external build host was required for the deployed browser.

## 5. Optimize and validate playback

The first full patched matrix passed, but repeated 4K CPU savings were initially modest. Inspection identified an expensive interleaved chroma copy in a texture path. Added NEON extraction to both relevant copy paths while preserving their different padding contracts and keeping a safe scalar tail for V-plane bounds.

Actual before/after functions passed 576 byte-equality/guard-page cases. Rebuilt Firefox, then passed the full 14-case matrix again. Repeated original test clips showed about 19.2% less browser CPU for 4K H.264 and 29.5% less for VP9, with zero counted dropped frames. Browser PSS did not consistently decrease.

A short six-second VP9 loop repeatedly incremented a drop counter. A packet-identical 18-second continuous fixture produced repeatable zero-drop comparisons. The original short-loop failures were not rewritten as passes, and looping behavior was not claimed fixed.

## 6. Verify the package and daily use

Staged Mozilla's install target without replacing the working browser. The package step stripped symbols as normal; a first raw-hash assertion correctly stopped. Independently reproduced `llvm-strip` on validated artifacts and required an exact staged match. Fixed the control-directory mode required by dpkg packaging.

The package passed 4K/VP9 playback and a public HTTPS H.264/AAC clip. A first cross-origin canvas read failed under browser security; a same-origin test document allowed an honest pixel read without disabling security. HTTPS certificate verification, signed active extensions, a pinned Bitwarden button and a rendered Bitwarden popup passed.

Installed native Firefox 158.0-1+fold1. All installed package checksums and dpkg audit passed. Verified actual Qualcomm hardware output again in the real profile with the normal launcher's environment and temporary diagnostics only; the browser exited cleanly. No vault/profile copy was used.

## 7. Fix environment integration and clean up

The real default-link test found that native Termux's `xdg-open` was a symlink to Android's `termux-open`, so links opened Samsung Internet despite Linux MIME associations. Preserved the Android opener using a local package diversion and added an asynchronous desktop HTTP/HTTPS route to native Firefox. Native and Debian links then reached the same native instance.

Kept automatic DPI/resolution, panel layout, icon sizes and dock behavior. The panel's audio plug-in only remembered Firefox as a media player; reversing that one cache addition exactly reconstructed the prior panel file hash. Several window sizes passed; actual physical folding/rotation/DeX monitor switching was not performed.

Deleted source/object/Cargo/cache trees, generated media, temporary profiles, decoder binaries, source archive and duplicate package; removed five task-only build packages. Removed the exact temporary SSH authorization and local access files. Preserved compact patches and evidence; no user-data backup or permanent decoder service was introduced.

## 8. Add update preservation and publish reusable work

Implemented an exact-package APT approval hook, FFmpeg ABI/codec-marker checks, post-update static verification and a general-update wrapper using an ephemeral Firefox preference. The phone's runtime and maintained update scripts were integrated, without running a full environment upgrade just for testing.

Host tests use synthetic packages. Native APT integration uses an isolated status file plus a refusing dpkg stub: protected replacements must stop before unpacking, while unrelated packages reach the stub. It verifies that the live package-status file is unchanged.

Added source/patch provenance, an upstream-change monitor, manual cross-build workflow, an isolated runtime harness, synthetic fixture generation and English maintenance/testing documentation. Published evidence omits raw personal logs, account data, keys, sessions, profiles and unrelated desktop configuration details. An optional rerun of the reorganized public harness was intentionally stopped. Its partial results remain separate and are not claimed as a second full matrix pass.

## What was not claimed

No universal fastest-browser result, all-codec hardware coverage, zero-copy rendering, measured battery saving, total-device memory reduction, audible A/V synchronization, physical Fold/DeX certification or upstream endorsement. Keeping an old Firefox forever is not update protection: a newer security release requires prompt porting/testing or an explicit temporary software-decoding choice.


## Firefox 159 maintenance

The source port, successful cross-build, browser-private Binder correction,
user-selected two-minute smoke validation and paired FFmpeg 9 deployment are
recorded in [the maintenance result](MAINTENANCE-159.md). This update does not
reuse the original Firefox 158 results as Firefox 159 certification.
