# Keeping the feature across environment updates

There are two separate requirements: retain hardware decoding and keep Firefox security fixes current. A fixed package version alone does not satisfy both. This workflow prevents silent replacement and makes the remaining maintenance visible.

## Local guard

The installer is for an **already tested** native Firefox. It does not build Firefox, restore a profile, enable a daemon or download/install an unknown browser.

The installed pieces are:

- `$PREFIX/libexec/firefox-mediacodec/update_guard.py`
- `$PREFIX/var/lib/firefox-mediacodec/approved.json`
- `$PREFIX/bin/fold-firefox-maintenance`
- `$PREFIX/etc/apt/apt.conf.d/90-firefox-mediacodec`

The APT pre-install hook uses the documented version-1 package-filename protocol. It allows Firefox only when package SHA256, version and architecture match an approval. FFmpeg candidates must retain the configured ABI aliases and H.264/VP9 NDK decoder markers. A post-invoke check verifies the installed protected binary hashes, required policy defaults and ABI presence. It is a cheap update-time check, not fresh playback certification.

The general-update wrapper creates a temporary Firefox-only APT preference for the currently validated version, preserves an existing main preferences file's contents, invokes the update command, removes the temporary file even on failure, and reports newer Firefox versions from repository metadata. It does not add a persistent `apt-mark hold` or silently call an old release “up to date.” Unrelated packages retain their ordinary update policy.

The original device's native `fold-update` and its maintained source were integrated with this wrapper. No full environment upgrade was performed just to test the protection; the actual general-update integration was simulated, and the APT hooks were exercised with refusing dpkg fixtures.

## Bootstrap approval for your own candidate

Do not treat the historic example package hash as a universal approval for your phone. Build/stage and run the complete matrix on your device first.

```sh
cp examples/approval-template.json .work/approved.json
python scripts/update_guard.py --manifest .work/approved.json approve /absolute/path/to/candidate.deb --validation .work/runtime/validation-REPLACE/summary.json
```

The validation must prove the exact package payload: normally run the matrix directly on the extracted `.deb` binaries. If tests used unstripped build artifacts and the package contains Mozilla-stripped versions, also supply `--strip-proof` with an independently verified source/staged hash mapping, matching the example in `evidence/package-strip-proof.json`.

Approval requires every named case, the correct software/hardware trial order, native untraced execution, expected `libxul`, actual decoded hardware output, clean exits, stable artifact fingerprints and package-to-tested-binary hashes. The approval file is a local maintenance policy, not a defense against a malicious administrator who can rewrite the guard itself.

Install the tested candidate through your normal reviewed local-package workflow, merge the two production preference defaults, then install protection:

```sh
python scripts/install_update_guard.py --manifest .work/approved.json
fold-firefox-maintenance status
```

Optional updater integration accepts explicit script paths containing exactly one `pkg upgrade -y` command:

```sh
python scripts/install_update_guard.py --manifest .work/approved.json --update-script "$HOME/fold8-linux/fold-update.sh"
```

For general Termux updates:

```sh
fold-firefox-maintenance protected-upgrade -- pkg upgrade -y
```

For a newly validated candidate, add its approval before asking APT to install it:

```sh
fold-firefox-maintenance approve /absolute/path/to/new-candidate.deb --validation /absolute/path/to/new-validation/summary.json
apt install /absolute/path/to/new-candidate.deb
fold-firefox-maintenance status
```

The production preferences are `media.ffmpeg.preferred=true` and `media.ffmpeg.mediacodec.enabled=true`. The examples use **default**, not locked, policy preferences, so an explicit user hardware-disable choice remains respected. Merge these into an existing policies file rather than replacing unrelated user policy.

## When upstream changes

1. Review the upstream-monitor result and Mozilla's security advisories. A failed monitor means maintenance is required, not that an update has been tested.
2. Update source/recipe/checksum pins, rebase the four feature patches and review native-host compatibility separately.
3. Build the candidate. A manual GitHub workflow supplies the pinned official cross-build route; it does not certify hardware on a hosted Linux runner.
4. Run all on-device gates and daily-use checks. A same-version string is not evidence; exact binary/package hashes matter.
5. Approve and promote only the validated package. Remove large development artifacts afterward.

If a security update cannot be ported promptly, explicitly choose between completing the port and temporarily using the current official Firefox with software decoding. Keeping the old build forever to preserve acceleration is not an acceptable maintenance strategy. No automatic no-risk rollback or cross-device hardware guarantee is claimed.

## Boundaries

Direct `dpkg -i`, manual library replacement, another package manager, Android firmware updates and removal/overriding of the APT hook are outside the hook's enforcement. The static FFmpeg ABI/marker checks cannot exclude every same-ABI codec regression. The post-check reports static installed state; run hardware playback tests after relevant runtime/driver updates. Other system libraries may also change behavior.

To intentionally return to the official browser, first remove this project's APT hook and updater integration, explicitly accept temporary software decoding, then install the current official package. Keep the normal user profile; no backup or separate stale browser installation is required by this project.

References: [APT hook protocol](https://manpages.debian.org/trixie/apt/apt.conf.5.en.html), [APT preferences](https://manpages.debian.org/trixie/apt/apt_preferences.5.en.html), [Termux package management](https://github.com/termux/termux-packages/wiki/Package-Management), [Mozilla Firefox security advisories](https://www.mozilla.org/en-US/security/known-vulnerabilities/firefox/).


When an installed hardware build still requires the older FFmpeg ABI, a general
update may explicitly use `protected-upgrade --keep-ffmpeg -- apt-get upgrade -y`.
This pins the installed FFmpeg version only within that command, alongside Firefox,
while preserving existing APT preferences. It does not approve a replacement or
relax the package hook. Deferred browser and codec security updates still require
prompt porting and validation. The default command does not pin FFmpeg implicitly.


The explicitly selected, bounded maintenance smoke protocol and exact codec/runtime
payload requirements are documented in [the Firefox 159 maintenance result](MAINTENANCE-159.md).
The default approval path remains the full matrix.
