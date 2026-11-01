#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Bounded native maintenance smoke check, not the full performance matrix."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = [('h264', 'h264.mp4', {}), ('vp9', 'vp9-continuous.webm', {}),
         ('av1-fallback', 'av1.webm', {'PROBE_EXPECT_SOFTWARE': '1'}),
         ('hardware-disabled', 'h264.mp4', {'PROBE_DISABLE_HARDWARE': '1'})]


def fingerprint(path):
    path = path.resolve()
    with path.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': checksum, 'bytes': path.stat().st_size}


def owned(marker):
    result = []
    token = ('FOLD_VALIDATION_RUN_ID=' + marker).encode() + b'\0'
    for proc in Path('/proc').iterdir():
        try:
            if not proc.name.isdigit() or proc.stat().st_uid != os.getuid():
                continue
            if (proc / 'stat').read_text().rsplit(')', 1)[1].split()[0] == 'Z':
                continue
            if token in (proc / 'environ').read_bytes():
                result.append(int(proc.name))
        except OSError:
            pass
    return result


def cleanup(marker):
    ids = owned(marker)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid in ids:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        until = time.monotonic() + 1
        while ids and time.monotonic() < until:
            time.sleep(.05)
            ids = owned(marker)
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--codec-dir', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--prior-seconds', type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.prior_seconds < 112:
        raise SystemExit('No time remains in the two-minute test budget')
    prefix = Path('/data/data/com.termux/files/usr')
    tracer = next(line.split(':', 1)[1].strip() for line in
                  Path('/proc/self/status').read_text().splitlines() if line.startswith('TracerPid:'))
    if not Path(sys.executable).resolve().is_relative_to(prefix) or tracer != '0':
        raise SystemExit('Use native Termux Python outside PRoot.')
    binary = args.binary.resolve()
    codecs = args.codec_dir.resolve()
    media = args.work.resolve() / 'test-media'
    for _, filename, _ in CASES:
        if not (media / filename).is_file():
            raise SystemExit('Missing prepared fixture: ' + filename)
    output = args.work.resolve() / ('smoke-' + str(time.time_ns()))
    output.mkdir(parents=True)
    started = time.monotonic()
    deadline = started + 112 - args.prior_seconds  # Reserve the final eight seconds for cleanup/hash checks.
    before = {name: fingerprint(binary.parent / name) for name in ('firefox', 'libxul.so')}
    binder = binary.parent / 'native-system/libbinder_ndk.so'
    if not binder.is_file():
        binder = codecs / 'libbinder_ndk.so'
    codec_paths = {name: codecs / name for name in ('libavcodec.so.63', 'libavutil.so.61')}
    codec_paths['libbinder_ndk.so'] = binder
    codec_before = {name: fingerprint(path) for name, path in codec_paths.items()}
    summary = {'protocol': 'maintenance-smoke-v1', 'stage': 'patched', 'complete': False,
               'deadline_enforced': True, 'budget_seconds': 120, 'prior_test_seconds': args.prior_seconds, 'cases': [],
               'system_binder': fingerprint(Path('/system/lib64/libbinder_ndk.so')),
               'artifact_fingerprints': before, 'codec_fingerprints': codec_before,
               'ffmpeg_abi': {'libavcodec': 63, 'libavutil': 61},
               'omitted': ['4K', '10-bit', 'streaming audio', 'concurrent resize', 'pacing', 'ABBA benchmarks']}
    env = {k: v for k, v in os.environ.items() if not k.startswith('PROBE_')
           and k not in ('LD_PRELOAD', 'LD_LIBRARY_PATH')}
    env.update(PROBE_ORDER='hardware', PROBE_NATIVE_DECODER='1', PROBE_REQUIRE_SELECTION_LOG='1',
               PROBE_FIREFOX_EXE=str(binary), FOLD_TEST_CODEC_DIR=str(codecs))
    for name, filename, options in CASES:
        entry = {'name': name, 'passed': False, 'rows': []}
        case_dir = output / name
        case_dir.mkdir()
        (case_dir / 'test-media').symlink_to(media, target_is_directory=True)
        current = dict(env, PROBE_MEDIA=filename, FOLD_FIREFOX_TEST_ROOT=str(case_dir))
        current.update(options)
        if name == 'hardware-disabled' and deadline - time.monotonic() < 20:
            current.update(PROBE_FINAL_SHORT_CHECK='1', PROBE_MIN_FRAMES='10')
            entry['brief_sample_ms'] = 800
        marker = os.urandom(16).hex()
        current['FOLD_VALIDATION_RUN_ID'] = marker
        proc = None
        print('START', name, flush=True)
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Two-minute suite budget exhausted')
            with (case_dir / 'stdout').open('w') as stdout, (case_dir / 'stderr').open('w') as stderr:
                proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/browser_probe.py')],
                                        env=current, stdout=stdout, stderr=stderr, start_new_session=True)
                proc.wait(timeout=min(35, remaining))
            rows = [json.loads(line) for line in (case_dir / 'stdout').read_text().splitlines()
                    if line.startswith('{')]
            entry.update(returncode=proc.returncode, rows=rows)
            entry['passed'] = (proc.returncode == 0 and len(rows) == 1 and rows[0].get('mode') == 'hardware'
                               and rows[0].get('checks_passed') and rows[0].get('cleanup_ok')
                               and rows[0].get('exit') == 0)
            if name in ('h264', 'vp9') and rows:
                expected = Path(codec_before['libavcodec.so.63']['path'])
                loaded = rows[0].get('loaded_decoder_libraries', [])
                entry['expected_codec_loaded'] = any(Path(p).resolve() == expected for p in loaded)
                entry['passed'] = entry['passed'] and entry['expected_codec_loaded']
        except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
            entry['error'] = str(exc)
        finally:
            entry['leftover_owned_pids'] = cleanup(marker)
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=1)
            if entry['leftover_owned_pids']:
                entry['passed'] = False
            for profile in case_dir.glob('profile-*'):
                if profile.is_dir() and not profile.is_symlink():
                    shutil.rmtree(profile)
        summary['cases'].append(entry)
        print('RESULT', name, bool(entry['passed']), flush=True)
        if not entry['passed']:
            break
    summary['artifacts_unchanged'] = before == {
        name: fingerprint(binary.parent / name) for name in ('firefox', 'libxul.so')}
    summary['codecs_unchanged'] = codec_before == {
        name: fingerprint(path) for name, path in codec_paths.items()}
    summary['elapsed_seconds'] = time.monotonic() - started
    summary['total_test_seconds'] = summary['elapsed_seconds'] + args.prior_seconds
    summary['complete'] = (len(summary['cases']) == len(CASES)
                           and all(case['passed'] for case in summary['cases'])
                           and summary['artifacts_unchanged'] and summary['codecs_unchanged']
                           and summary['total_test_seconds'] <= 120)
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('SUMMARY', output / 'summary.json', flush=True)
    return 0 if summary['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
