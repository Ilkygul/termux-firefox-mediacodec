# SPDX-License-Identifier: MPL-2.0
"""Exercise real process-group cleanup without building or opening Firefox."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


def native_process_groups_supported():
    if sys.platform not in ('linux', 'android'):
        return False
    status = Path('/proc/self/status').read_text()
    tracer = next(line.split(':', 1)[1].strip() for line in status.splitlines()
                  if line.startswith('TracerPid:'))
    return tracer == '0'


@unittest.skipUnless(native_process_groups_supported(),
                     'Run directly on Linux/Termux; PRoot tracing changes signal-stop states')
class NativeStageTests(unittest.TestCase):
    def test_full_power_retains_build_date_and_retries_on_memory_pressure(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/native-stage.py'
        with tempfile.TemporaryDirectory(prefix='native-power-test-') as directory:
            work = Path(directory)
            (work / 'source-baseline').mkdir()
            (work / 'obj-native').mkdir()
            (work / 'obj-native/buildid.h').write_text('#define MOZ_BUILDID 20261101204821\n')
            tools = work / 'bin'
            tools.mkdir()
            (tools / 'python').symlink_to(sys.executable)
            (work / 'native-build-env.py').write_text(
                'import os\ndef build_env():\n'
                f' env=os.environ.copy();env["PATH"]={str(tools)!r}+":"+env["PATH"];return env\n'
            )
            report = work / 'child.json'
            (work / 'source-baseline/mach').write_text(
                'import os,sys,json,time\nfrom pathlib import Path\n'
                f'Path({str(report)!r}).write_text(json.dumps({{"cpus":list(os.sched_getaffinity(0)),'
                '"date":os.environ.get("MOZ_BUILD_DATE"),"args":sys.argv}))\n'
                'time.sleep(300)\n'
            )
            metrics = work / 'metrics.json'
            metrics.write_text(json.dumps({'timestamp': time.time(), 'cpu_temp': 99, 'cpu': 99}))
            memory = work / 'meminfo'
            memory.write_text('MemAvailable: 4194304 kB\n')
            runner = work / 'native-stage.py'
            runner.write_text(script.read_text().replace(
                '/data/data/com.termux/files/home/.config/fold8/widget/metrics.json', str(metrics),
            ).replace('/proc/meminfo', str(memory)).replace(
                'time.sleep(2 if options.full_power else 10)', 'time.sleep(0.02)',
            ))
            child = None
            with (work / 'controller.log').open('w') as output:
                controller = subprocess.Popen(
                    [sys.executable, str(runner), 'build', '--jobs', '6', '--full-power'],
                    stdout=output, stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 10
                    state_file = work / 'native-stage-current.json'
                    while time.monotonic() < deadline:
                        try:
                            data = json.loads(report.read_text())
                            state = json.loads(state_file.read_text())
                            break
                        except (OSError, ValueError):
                            pass
                        if controller.poll() is not None:
                            self.fail((work / 'controller.log').read_text())
                        time.sleep(0.02)
                    else:
                        self.fail('Full-power child did not start')
                    child = state['pid']
                    self.assertEqual(set(data['cpus']), set(os.sched_getaffinity(0)))
                    self.assertEqual(data['date'], '20261101204821')
                    self.assertIn('-j6', data['args'])
                    self.assertEqual(data['args'][-2:], ['--priority', 'normal'])
                    time.sleep(0.1)
                    self.assertIsNone(controller.poll(), 'CPU/temperature soft limits affected full-power mode')
                    memory.write_text('MemAvailable: 524288 kB\n')
                    self.assertEqual(controller.wait(timeout=5), 75)
                    self.assertFalse(Path(f'/proc/{child}').exists(), 'Resource retry left a child behind')
                    state = json.loads(state_file.read_text())
                    self.assertEqual(state['status'], 'stopped')
                    self.assertIn('resource_restart', state)
                finally:
                    if controller.poll() is None:
                        controller.kill()
                        controller.wait()
                    if child is not None and Path(f'/proc/{child}').exists():
                        os.killpg(child, signal.SIGCONT)
                        os.killpg(child, signal.SIGKILL)

    def test_termination_resumes_and_cleans_up_paused_build(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/native-stage.py'
        with tempfile.TemporaryDirectory(prefix='native-stage-test-') as directory:
            work = Path(directory)
            source = work / 'source-baseline'
            source.mkdir()
            tools = work / 'bin'
            tools.mkdir()
            (tools / 'python').symlink_to(sys.executable)
            (work / 'native-build-env.py').write_text(
                'import os\ndef build_env():\n'
                f' env=os.environ.copy();env["PATH"]={str(tools)!r}+":"+env["PATH"];return env\n'
            )
            (source / 'mach').write_text('import time\ntime.sleep(300)\n')
            metrics = work / 'metrics.json'
            metrics.write_text(json.dumps({'timestamp': time.time(), 'cpu_temp': 90, 'cpu': 0}))
            runner = work / 'native-stage.py'
            runner.write_text(script.read_text().replace(
                '/data/data/com.termux/files/home/.config/fold8/widget/metrics.json',
                str(metrics),
            ).replace('time.sleep(2 if options.full_power else 10)', 'time.sleep(0.02)'))
            child = None
            with (work / 'controller.log').open('w') as output:
                controller = subprocess.Popen(
                    [sys.executable, str(runner), 'configure'],
                    stdout=output, stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        status = work / 'native-stage-current.json'
                        try:
                            state = json.loads(status.read_text())
                            child = state['pid']
                            process_status = Path(f'/proc/{child}/status').read_text()
                            if state.get('resource_pause') and '\nState:\tT' in process_status:
                                break
                        except (OSError, ValueError):
                            pass
                        if controller.poll() is not None:
                            self.fail((work / 'controller.log').read_text())
                        time.sleep(0.02)
                    else:
                        self.fail('Build did not enter the expected stopped state')
                    controller.send_signal(signal.SIGTERM)
                    self.assertEqual(controller.wait(timeout=5), 128 + signal.SIGTERM)
                    self.assertFalse(Path(f'/proc/{child}').exists(), 'Paused child was left behind')
                    state = json.loads(status.read_text())
                    self.assertEqual(state['status'], 'stopped')
                    self.assertIsNotNone(state['returncode'])
                finally:
                    if controller.poll() is None:
                        controller.kill()
                        controller.wait()
                    if child is not None and Path(f'/proc/{child}').exists():
                        os.killpg(child, signal.SIGCONT)
                        os.killpg(child, signal.SIGKILL)


if __name__ == '__main__':
    unittest.main()
