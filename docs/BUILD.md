# Build the pinned candidate

The source archive, official Termux recipe revision, 32 official patch checksums and nine local patch checksums are recorded in [`sources.json`](../sources.json). They identify the successfully built source. **They do not make an old Firefox release safe to keep indefinitely.** Rebase the pins and patches for newer security releases.

## Official Linux cross-build route

Use a Linux x86_64 host with Docker and sufficient memory/disk space for a Firefox build. The script pins the official Termux container digest and recipe revision. It never installs a browser on the phone.

```sh
bash scripts/build-on-linux.sh baseline /absolute/path/to/termux-firefox-build
bash scripts/build-on-linux.sh patched /absolute/path/to/termux-firefox-build
```

The baseline requires a clean recipe checkout. The patched stage copies all four feature patches into `x11-packages/firefox` and rebuilds Firefox. The official builder downloads source and dependencies. Outputs remain in the official Termux output directory; container/revision evidence is recorded there. No external cross-build was used for the original deployed browser; this is the supplied alternative route.

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

The wrapper targets API 24, uses ThinLTO, one build job by default, low build priority, two linker threads and affinity to the two highest-frequency available CPU cores. The object directory and Cargo/cache data remain under `.work/native`. No updater or browser installation runs here.

Use `--jobs 2` only when two build tasks fit your available memory. Mozilla's
jobserver also controls Cargo; `CARGO_BUILD_JOBS=1` alone does not override it.
The controller checks memory and the existing desktop metrics cache every ten
seconds. Compilation pauses below 1.5 GiB available memory, at a fresh CPU
sensor temperature of at least 80 °C, or at a fresh total CPU load of at least
85%. It resumes above 2 GiB, below 70 °C and below 65% CPU load. Configuration
uses 512/768 MiB memory thresholds instead. Missing/stale desktop metrics are
ignored; memory checks still run. These are local responsiveness settings,
not measured universal safety limits or firmware thermal limits.

Only the build's own process group is paused. SIGTERM to the controller resumes
and terminates that group, waits for cleanup, and records a stopped state.
The JSON PID identifies the child build, not its controller. No monitoring
service is installed; the controller ends with the build. A real process-group
unit test covers stopping a paused child and confirms that it is reaped. The
resource controls were added after the original Firefox 158 deployment; this
does not claim another complete 158 build or a new browser playback result.

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
