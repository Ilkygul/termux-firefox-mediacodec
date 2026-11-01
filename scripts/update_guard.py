#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Prevent an unvalidated Firefox replacement; no resident process or network I/O."""
from __future__ import annotations
import argparse
import contextlib
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile

SCHEMA = 1
CASES = {'h264', 'h264-4k', 'vp9', 'av1-fallback', '10bit-fallback',
         'streaming-aac', 'h264-selection', 'vp9-selection', 'hardware-disabled',
         'concurrent-resize', 'h264-4k-pacing', 'vp9-pacing',
         'h264-4k-abba', 'vp9-abba'}
class GuardError(Exception):
    pass

def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def load(path):
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise GuardError(f'Cannot read {path}: {exc}') from exc
    return value

class Guard:
    def __init__(self, prefix, manifest=None):
        self.prefix = Path(prefix).absolute()
        self.manifest = Path(manifest) if manifest else self.prefix / 'var/lib/firefox-mediacodec/approved.json'
    def tool(self, name):
        local = self.prefix / 'bin' / name
        return str(local) if local.is_file() else name
    def run(self, name, *args):
        result = subprocess.run([self.tool(name), *map(str, args)], capture_output=True, text=True)
        if result.returncode:
            raise GuardError(f'{name} failed: {result.stderr.strip()}')
        return result.stdout
    def policy(self, allow_empty=False):
        policy = load(self.manifest)
        if policy.get('schema') != SCHEMA or not isinstance(policy.get('approved_firefox'), list) or (not policy['approved_firefox'] and not allow_empty):
            raise GuardError('Missing supported approval manifest; do not silently replace Firefox.')
        for entry in policy['approved_firefox']:
            if set(entry.get('binaries', {})) != {'firefox', 'libxul.so'} or not entry.get('version') or not entry.get('architecture'):
                raise GuardError('Approval entries must identify both protected binaries, version and architecture.')
            if not all(re.fullmatch(r'[0-9a-f]{64}', value) for value in [entry.get('package_sha256', ''), *entry['binaries'].values()]):
                raise GuardError('Invalid approval checksum.')
        if set(policy.get('ffmpeg_abi', {})) != {'libavcodec', 'libavutil'} or not all(isinstance(v, int) and v > 0 for v in policy['ffmpeg_abi'].values()):
            raise GuardError('Required FFmpeg ABI must be explicit.')
        return policy
    def metadata(self, package):
        fields = self.run('dpkg-deb', '--field', package, 'Package', 'Version', 'Architecture')
        values = dict(line.split(': ', 1) for line in fields.splitlines() if ': ' in line)
        if not all(values.get(key) for key in ('Package', 'Version', 'Architecture')):
            raise GuardError('Invalid package metadata.')
        return values
    def payload(self, package, names=(), codec_abi=None):
        """Stream selected members; never extract package paths to the filesystem."""
        wanted = {str(Path(n)).lstrip('./'): n for n in names}
        found = {}; members = set(); codec_features = set()
        command = [self.tool('dpkg-deb'), '--fsys-tarfile', str(package)]
        with tempfile.TemporaryFile() as errors:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors)
            try:
                with tarfile.open(fileobj=proc.stdout, mode='r|') as archive:
                    for member in archive:
                        name = member.name.removeprefix('./').lstrip('/')
                        members.add(name)
                        codeclib = bool(codec_abi and re.search(r'(?:^|/)libavcodec\.so\.' + str(codec_abi) + r'(?:\.[0-9]+)*$', name) and member.isfile())
                        if member.isfile() and (name in wanted or codeclib):
                            stream = archive.extractfile(member); checksum = hashlib.sha256(); tail = b''
                            while block := stream.read(1024 * 1024):
                                checksum.update(block)
                                if codeclib:
                                    chunk = tail + block
                                    for token in (b'h264_mediacodec', b'vp9_mediacodec', b'ndk_codec'):
                                        if token in chunk: codec_features.add(token.decode())
                                    tail = chunk[-64:]
                            if name in wanted:
                                if wanted[name] in found: raise GuardError('Duplicate protected package member.')
                                found[wanted[name]] = checksum.hexdigest()
                if proc.wait() != 0:
                    errors.seek(0); raise GuardError(errors.read().decode(errors='replace'))
            finally:
                if proc.stdout: proc.stdout.close()
                if proc.poll() is None: proc.kill(); proc.wait()
        return found, members, codec_features
    def inspect_package(self, package):
        meta = self.metadata(package)
        if meta['Package'] not in ('firefox', 'ffmpeg'):
            return meta
        policy = self.policy()
        if meta['Package'] == 'firefox':
            checksum = digest(package)
            if not any(entry['version'] == meta['Version'] and entry['architecture'] == meta['Architecture']
                       and entry['package_sha256'] == checksum for entry in policy['approved_firefox']):
                raise GuardError(f"Firefox {meta['Version']} is NOT an approved hardware-decoding package. "
                                 'Update blocked before unpacking. Rebuild and validate the current Firefox release, '
                                 'then approve the exact package. Security updates may be pending; run fold-firefox-maintenance status.')
        else:
            abi = policy['ffmpeg_abi']; _, members, features = self.payload(package, codec_abi=abi['libavcodec'])
            root = str(self.prefix).lstrip('/') + '/lib/'
            required = {root + 'libavcodec.so.' + str(abi['libavcodec']), root + 'libavutil.so.' + str(abi['libavutil'])}
            if not required <= members or features != {'h264_mediacodec', 'vp9_mediacodec', 'ndk_codec'}:
                raise GuardError('FFmpeg candidate lacks the required ABI aliases or MediaCodec/NDK codec markers. '
                                 'Port and validate before upgrading this dependency.')
        return meta
    def installed(self):
        policy = self.policy()
        version = self.run('dpkg-query', '-W', '-f=${Version}', 'firefox').strip()
        entry = next((e for e in policy['approved_firefox'] if e['version'] == version and
                      all((self.prefix / 'lib/firefox' / name).is_file() and
                          digest(self.prefix / 'lib/firefox' / name) == checksum
                          for name, checksum in e['binaries'].items())), None)
        if not entry: raise GuardError('Installed Firefox does not match an approved hardware build.')
        prefs = load(self.prefix / 'lib/firefox/distribution/policies.json')['policies']['Preferences']
        for name in ('media.ffmpeg.preferred', 'media.ffmpeg.mediacodec.enabled'):
            if prefs.get(name, {}).get('Value') is not True:
                raise GuardError(f'Missing enabled default: {name}')
        for name, major in policy['ffmpeg_abi'].items():
            if not (self.prefix / 'lib' / f'{name}.so.{major}').is_file():
                raise GuardError(f'Required runtime ABI disappeared: {name}.so.{major}')
        return {'version': version, 'approved': True, 'runtime_abi_present': True}
    def pending(self, installed):
        available = []
        result = subprocess.run([self.tool('apt-cache'), 'madison', 'firefox'], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            fields = line.split('|')
            if len(fields) < 2: continue
            candidate = fields[1].strip()
            if subprocess.run([self.tool('dpkg'), '--compare-versions', candidate, 'gt', installed], capture_output=True).returncode == 0:
                available.append(candidate)
        return sorted(set(available))
    def status(self, emit=True):
        state = self.installed(); state['newer_repository_versions'] = self.pending(state['version'])
        if emit:
            print(f"Hardware Firefox {state['version']}: approved; required FFmpeg ABI present.")
            if state['newer_repository_versions']:
                print('ACTION REQUIRED: newer Firefox repository versions are available: ' + ', '.join(state['newer_repository_versions']), file=sys.stderr)
                print('Firefox security updates may be pending. Rebuild/test the newer release; do not leave it indefinitely deferred.', file=sys.stderr)
            print('This is a file/policy/ABI check, not a fresh hardware-playback test.')
        return state
    def approve(self, package, validation_path, strip_path):
        validation = load(validation_path); proof = load(strip_path) if strip_path else {}
        if validation.get('stage') != 'patched' or validation.get('complete') is not True or validation.get('artifacts_unchanged') is not True:
            raise GuardError('A completed patched runtime validation with unchanged artifacts is required.')
        cases = validation.get('cases', [])
        if len(cases) != len(CASES) or {c.get('name') for c in cases} != CASES:
            raise GuardError('The full 14-case runtime matrix is required.')
        for case in cases:
            rows = case.get('rows', [])
            if not case.get('passed') or not rows or not all(r.get('checks_passed') and r.get('cleanup_ok') and r.get('exit') == 0 for r in rows):
                raise GuardError('Every case must contain passed runtime rows and clean shutdown.')
            expected_modes = ['software', 'hardware', 'hardware', 'software'] if case['name'].endswith('-abba') else ['software', 'hardware']
            if [r.get('mode') for r in rows] != expected_modes:
                raise GuardError('Required software/hardware comparison rows are missing.')
            for row in rows:
                if not row.get('native_direct') or not row.get('expected_libxul_loaded') or str(row.get('tracer_pid', '')).split(':')[-1].strip() != '0':
                    raise GuardError('Validation must prove direct, untraced native execution and the expected libxul.')
                if row.get('mode') == 'hardware' and case['name'] not in ('av1-fallback', '10bit-fallback', 'hardware-disabled'):
                    if not row.get('output_hardware_decoder') or not row.get('hardware_decoder_names'):
                        raise GuardError('Actual decoded hardware output and codec-start evidence are required.')
        meta = self.metadata(package)
        if meta['Package'] != 'firefox' or meta['Architecture'] != 'aarch64': raise GuardError('Approve a native AArch64 Firefox package.')
        names = [str(self.prefix / 'lib/firefox' / name).lstrip('/') for name in ('firefox', 'libxul.so')]
        actual, _, _ = self.payload(package, names)
        binaries = {}
        for name, member in zip(('firefox', 'libxul.so'), names):
            item = proof.get(name, {})
            validated = validation.get('artifact_fingerprints', {}).get(name, {}).get('sha256')
            direct = bool(validated and actual.get(member) == validated)
            stripped = bool(validated and item.get('validated_unstripped_sha256') == validated and item.get('matches_independent_llvm_strip') is True and actual.get(member) == item.get('staged_sha256'))
            if not (direct or stripped):
                raise GuardError('Package payload is not the validated artifact and lacks an exact strip proof.')
            binaries[name] = actual[member]
        policy = self.policy(allow_empty=True); entry = {'version': meta['Version'], 'architecture': meta['Architecture'],
            'package_sha256': digest(package), 'binaries': binaries, 'validation_sha256': digest(validation_path)}
        policy['approved_firefox'] = [e for e in policy['approved_firefox'] if e['package_sha256'] != entry['package_sha256']] + [entry]
        temporary = self.manifest.with_suffix('.tmp'); temporary.write_text(json.dumps(policy, indent=2) + '\n'); temporary.chmod(0o600); os.replace(temporary, self.manifest)
        print('Approved exact tested package:', meta['Version'])
    def upgrade(self, command, keep_ffmpeg=False):
        state = self.status()
        if not command: raise GuardError('Provide an update command after --.')
        current = self.prefix / 'etc/apt/preferences'
        base = current.read_text() if current.exists() else ''
        dependency_pin = ''
        if keep_ffmpeg:
            version = self.run('dpkg-query', '-W', '-f=${Version}', 'ffmpeg').strip()
            if not re.fullmatch(r'[0-9A-Za-z.+:~_-]+', version):
                raise GuardError('Cannot identify the installed FFmpeg version.')
            dependency_pin = f'\nPackage: ffmpeg\nPin: version {version}\nPin-Priority: 1001\n'
            print(f'Keeping FFmpeg {version} for this update only. Review deferred dependency/security updates.', flush=True)
        with tempfile.TemporaryDirectory(prefix='firefox-update-') as directory:
            pin = Path(directory) / 'preferences'
            pin.write_text(base + f"\nPackage: firefox\nPin: version {state['version']}\nPin-Priority: 1001\n" + dependency_pin)
            print('Keeping the currently validated Firefox during this general update. No persistent apt hold is set.', flush=True)
            rc = subprocess.run([*command, '-o', 'Dir::Etc::preferences=' + str(pin)]).returncode
        self.status()
        return rc

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default=os.environ.get('PREFIX', '/data/data/com.termux/files/usr'))
    parser.add_argument('--manifest', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('apt-hook')
    status = sub.add_parser('status'); status.add_argument('--json', action='store_true')
    candidate = sub.add_parser('inspect'); candidate.add_argument('package', type=Path)
    approve = sub.add_parser('approve'); approve.add_argument('package', type=Path); approve.add_argument('--validation', type=Path, required=True); approve.add_argument('--strip-proof', type=Path)
    upgrade = sub.add_parser('protected-upgrade'); upgrade.add_argument('--keep-ffmpeg', action='store_true'); upgrade.add_argument('update_command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv); guard = Guard(args.prefix, args.manifest)
    try:
        if args.command == 'apt-hook':
            fd = int(os.environ.get('APT_HOOK_INFO_FD', '0'))
            with os.fdopen(os.dup(fd)) as stream:
                for line in stream:
                    package = line.rstrip('\n')
                    if package: guard.inspect_package(package)
        elif args.command == 'status':
            state = guard.status(emit=not args.json)
            if args.json: print(json.dumps(state, indent=2))
        elif args.command == 'inspect': print(json.dumps(guard.inspect_package(args.package)))
        elif args.command == 'approve': guard.approve(args.package, args.validation, args.strip_proof)
        elif args.command == 'protected-upgrade':
            command = args.update_command
            if command[:1] == ['--']: command = command[1:]
            return guard.upgrade(command, args.keep_ffmpeg)
        return 0
    except (GuardError, OSError, ValueError, KeyError, tarfile.TarError) as exc:
        print('Firefox MediaCodec guard: ' + str(exc), file=sys.stderr)
        return 42
if __name__ == '__main__': raise SystemExit(main())
