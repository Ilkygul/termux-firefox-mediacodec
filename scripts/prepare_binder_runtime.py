#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Build the small browser-private Termux Binder forwarder; never install it."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prefix = Path(os.environ.get('PREFIX', '/data/data/com.termux/files/usr')).resolve()
    if not Path(sys.executable).resolve().is_relative_to(prefix):
        raise SystemExit('Run with native Termux Python, outside PRoot.')
    output = args.output.resolve()
    if output.is_relative_to(prefix / 'lib'):
        raise SystemExit('Stage outside the installed library directory.')
    if output.exists():
        raise SystemExit('Output already exists; inspect it rather than silently overwriting it.')
    pins = json.loads((ROOT / 'runtime-pins.json').read_text())
    patch = ROOT / pins['patch']
    if sha(patch) != pins['patch_sha256']:
        raise SystemExit('Runtime patch checksum mismatch.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fold-binder-') as directory:
        work = Path(directory)
        for entry in pins['sources']:
            target = work / entry['name']
            with urllib.request.urlopen(entry['url'], timeout=30) as response:
                target.write_bytes(response.read())
            if sha(target) != entry['sha256']:
                raise SystemExit('Pinned runtime source checksum mismatch: ' + entry['name'])
        subprocess.run([str(prefix / 'bin/patch'), '--batch', '--forward', '-p1', '-i', str(patch)],
                       cwd=work, check=True)
        subprocess.run([str(prefix / 'bin/clang'), '--target=aarch64-linux-android28',
                        '-shared', '-fPIC', '-O2', '-Wno-deprecated-declarations',
                        '-Wl,-soname,libbinder_ndk.so', '-Wl,-rpath,' + str(prefix / 'lib'),
                        '-L' + str(prefix / 'lib'), '-I' + str(work),
                        str(work / 'libbinder_ndk-wrapper.c'), '-ltermux-platform-ns', '-ldl',
                        '-o', str(output)], check=True)
    output.chmod(0o755)
    receipt = {'upstream_revision': pins['upstream_revision'], 'patch_sha256': pins['patch_sha256'],
               'binary_sha256': sha(output), 'output': str(output), 'not_installed': True,
               'license': pins['upstream_license']}
    output.with_suffix('.build.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
