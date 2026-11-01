# Build the pinned candidate

The source archive, official Termux recipe revision, 35 official patch checksums and nine local patch checksums are recorded in [`sources.json`](../sources.json). On this candidate branch they identify the Firefox 159 source used by the successful cross-build. The archived successful-build and playback receipts belong to Firefox 158; they do not validate the new candidate. **They do not make an old Firefox release safe to keep indefinitely.** Rebase the pins and patches for newer security releases.

## Official Linux cross-build route

Use a Linux x86_64 host with Docker and sufficient memory/disk space for a Firefox build. The script pins the official Termux container digest and recipe revision. It never installs a browser on the phone.

```sh
bash scripts/build-on-linux.sh baseline /absolute/path/to/termux-firefox-build
bash scripts/build-on-linux.sh patched /absolute/path/to/termux-firefox-build
```

The baseline requires a clean recipe checkout. The patched stage copies all four feature patches into `x11-packages/firefox` and rebuilds Firefox. The official builder downloads source and dependencies. Outputs remain in the official Termux output directory; container/revision evidence is recorded there. No external cross-build was used for the original deployed browser; this is the supplied alternative route.

Both stages apply the same build-host ThinLTO selector and enable it. The baseline
omits the four runtime feature patches. This keeps link optimization from
confounding a future baseline/patched comparison; no new comparison is claimed.

The cross-build defaults to two build jobs. `FOLD_FIREFOX_BUILD_JOBS` selects a
different positive integer for a larger build host. The wrapper passes it through
Termux's explicit `-jN` option, which the pinned Firefox recipe forwards to
`mach build`. Setting `CARGO_BUILD_JOBS` alone does not override Mozilla's jobserver.
The completed build records the selected job count beside its other receipts.
This change does not alter or restart an already running hosted build.

Do not distribute official Firefox branding merely because the source configuration uses it. Review the upstream redistribution/trademark requirements separately.

## Reproduce the native on-phone route

Run in **native Termux**, not Debian/PRoot. Install build prerequisites appropriate to the pinned official Termux recipe. The original build used Rust 1.99.1, Clang 21.1.8-3, Python 3.14.6, node 24.18, cbindgen 0.29.4, ninja and libcpufeatures, in addition to the ordinary Firefox development dependencies. Those historic versions may not remain available in a rolling repository; record actual dependency/toolchain versions for every rebuild.

```sh
python scripts/prepare_sources.py --native --work .work/native
```

This downloads and verifies the source archive and official patches, applies the host patches followed by the feature patches, updates the vendored source checksum, creates the isolated mozconfig and copies the successful native runner settings into `.work/native`. It refuses to overwrite an existing source tree. `--baseline` omits the four feature patches for a separate baseline work directory.

Build cbindgen in the isolated tool directory rather than replacing a global installation:

```sh
CARGO_HOME="$PWD/.work/native/cargo-cache" cargo install --locked --root "$PWD/.work/native/native-build-tools" --version 0.29.4 cbindgen
python .work/native/native-stage.py configure
python .work/native/native-stage.py build --jobs 1
```

The wrapper targets API 24, uses ThinLTO, one build job by default, low build priority, two linker threads and affinity to the two highest-frequency available CPU cores. The object directory and Cargo/cache data remain under `.work/native`. No updater or browser installation runs here. Using `--jobs 2` enables two build tasks, including Cargo via Mozilla's jobserver; `CARGO_BUILD_JOBS=1` alone does not override that jobserver. The active candidate was resumed incrementally with `--jobs 1` after two simultaneous Rust compilations consumed unnecessary memory. The initial 3/4 GiB pause/resume thresholds also stalled a single Rust task while it retained memory; the maintained thresholds below reserve 1.5 GiB instead. They are local responsiveness settings, not measured universal safety limits.

The controller samples available memory and the existing desktop metrics cache every
10 seconds. During compilation it pauses only its own process group below 1.5 GiB
available memory, at a fresh CPU temperature of at least 80 °C, or at a fresh total
CPU utilization of at least 85%. It resumes above 2 GiB, below 70 °C and below 65%
CPU utilization. Configuration uses 512/768 MiB memory thresholds instead. Missing
or stale desktop metrics are ignored; memory checks still run. Temperature values
use this environment's existing highest-readable CPU sensor, not a universal SoC
junction-temperature measurement. These are conservative local build settings,
not firmware thermal limits. Android's own thermal controls remain enabled.

No new monitoring service is installed. The controller exits when its build ends.
Send SIGTERM to the controller process for cleanup: it resumes a paused build,
terminates its own process group and waits for it. A forced SIGKILL cannot run that
cleanup. The running browser, desktop and unrelated user workloads are untouched.
The JSON status contains the child build PID; it is not the controller PID.

The preparation/runner scripts are the maintained form of the successful native settings. The public repository layout was reorganized after deployment; the original complete native build is proven by the archived receipts, not by a claim that a second full build was performed after that reorganization.

## Stage instead of replacing the working browser

For a `.deb` candidate:

```sh
mkdir -p .work/candidate
# Run natively; this extracts files but does not execute maintainer scripts.
dpkg-deb --extract /absolute/path/to/firefox-candidate.deb .work/candidate
```

The test binary is normally:

```text
.work/candidate/data/data/com.termux/files/usr/lib/firefox/firefox
```

Use that absolute binary path with `scripts/validate_runtime.py`. The full test matrix uses disposable profiles, enables feature preferences only inside them and requires actual hardware output. A successful compile or patch application alone is not approval.

If building a native package manually, use Mozilla's `DESTDIR` installation target into an isolated directory. Mozilla's normal packager strips symbol tables. Either test the exact staged package binaries, or independently reproduce stripping and record the link from tested unstripped artifacts to staged hashes. Never copy a user profile into a package.

Use a distinct local package revision, such as `158.0-1+mediacodec.1`, without making it sort above future upstream security releases. Candidate package metadata, hash and actual payload must be approved together. No prebuilt `.deb` is included in this repository.


## Faster native builds on this phone

After configuration, `bash .work/native/native-build.sh 6` uses all CPUs available
to the controller, six build tasks and Mozilla's explicit `--priority normal`.
The ordinary `mach build` default is idle priority; affinity alone does not
remove that setting. `native-stage.py build --jobs 6 --full-power` runs one such
attempt. The helper accepts one to eight jobs and retries only its explicit
memory-pressure exit (75), reducing tasks to four, two and one. Compiler errors
are reported directly, without speculative retries.

Full-power mode checks available memory every two seconds. Below 1 GiB it stops
only its own build group, retains completed objects and requests a retry; it does
not freeze compilers while waiting for them to release their own memory. It uses
no software CPU-utilization or temperature pause threshold. Android's thermal
controls remain enabled. RAM is used on demand, with no fixed per-build quota.

An existing object directory's build ID is retained during incremental resumes.
This avoids regenerating timestamp-dependent Rust code merely because the task
count changed. Use a fresh prepared work directory for a new source release.
The conservative `native-stage.py` defaults remain available. Neither mode adds
a resident monitoring service or installs a browser.
