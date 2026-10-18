# SPDX-License-Identifier: MPL-2.0
"""Control-flow/package integrity tests. These are NOT hardware playback results."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('update_guard', ROOT / 'scripts/update_guard.py')
g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.prefix = self.root/'prefix'; self.prefix.mkdir()
        self.manifest = self.root/'approved.json'; self.guard = g.Guard(self.prefix, self.manifest)
        self.browser = self.package('firefox','1.0+hw', {'lib/firefox/firefox':b'test executable', 'lib/firefox/libxul.so':b'test library'})
        self.policy = {'schema':1,'approved_firefox':[{'version':'1.0+hw','architecture':'aarch64','package_sha256':g.digest(self.browser),'binaries':{'firefox':__import__('hashlib').sha256(b'test executable').hexdigest(),'libxul.so':__import__('hashlib').sha256(b'test library').hexdigest()}}],'ffmpeg_abi':{'libavcodec':62,'libavutil':60}}
        self.manifest.write_text(json.dumps(self.policy))
    def package(self, name, version, files):
        directory = self.root/(name+'-'+version); directory.mkdir(); control=directory/'DEBIAN'; control.mkdir(); control.chmod(0o755)
        (control/'control').write_text(f'Package: {name}\nVersion: {version}\nArchitecture: aarch64\nMaintainer: Test <test@example.invalid>\nDescription: Synthetic guard unit fixture, not a browser\n')
        for relative,data in files.items():
            p=directory/str(self.prefix).lstrip('/')/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        out=directory.with_suffix('.deb');subprocess.run(['dpkg-deb','--build',str(directory),str(out)],check=True,capture_output=True);return out
    def test_exact_approved_package(self): self.assertEqual(self.guard.inspect_package(self.browser)['Package'],'firefox')
    def test_new_official_version_rejected(self):
        candidate=self.package('firefox','2.0',{})
        with self.assertRaisesRegex(g.GuardError,'NOT an approved'):self.guard.inspect_package(candidate)
    def test_same_version_different_payload_rejected(self):
        modified=self.root/'modified.deb';modified.write_bytes(self.browser.read_bytes()+b'changed')
        with self.assertRaises(g.GuardError):self.guard.inspect_package(modified)
    def test_unrelated_update_does_not_require_manifest(self):
        other=self.package('other-app','1.0',{});self.manifest.unlink();self.assertEqual(self.guard.inspect_package(other)['Package'],'other-app')
    def test_missing_manifest_blocks_browser(self):
        self.manifest.unlink()
        with self.assertRaises(g.GuardError):self.guard.inspect_package(self.browser)
    def test_compatible_ffmpeg_has_required_aliases_and_markers(self):
        package=self.package('ffmpeg','8.1',{'lib/libavcodec.so.62':b'h264_mediacodec vp9_mediacodec ndk_codec', 'lib/libavutil.so.60':b'lib'})
        self.assertEqual(self.guard.inspect_package(package)['Package'],'ffmpeg')
    def test_new_ffmpeg_abi_blocked(self):
        package=self.package('ffmpeg','9.0',{'lib/libavcodec.so.63':b'h264_mediacodec vp9_mediacodec ndk_codec', 'lib/libavutil.so.61':b'lib'})
        with self.assertRaisesRegex(g.GuardError,'required ABI'):self.guard.inspect_package(package)
    def test_ffmpeg_without_ndk_codec_blocked(self):
        package=self.package('ffmpeg','8.2',{'lib/libavcodec.so.62':b'h264_mediacodec vp9_mediacodec', 'lib/libavutil.so.60':b'lib'})
        with self.assertRaises(g.GuardError):self.guard.inspect_package(package)
    def test_streams_exact_protected_payload_hashes(self):
        name=str(self.prefix/'lib/firefox/libxul.so').lstrip('/');found,_,_=self.guard.payload(self.browser,[name]);self.assertEqual(found[name],self.policy['approved_firefox'][0]['binaries']['libxul.so'])
    def test_approval_rejects_incomplete_runtime_validation(self):
        validation=self.root/'validation.json';validation.write_text(json.dumps({'stage':'patched','complete':False}));proof=self.root/'proof.json';proof.write_text('{}')
        with self.assertRaisesRegex(g.GuardError,'completed patched'):self.guard.approve(self.browser,validation,proof)
    def test_approval_requires_all_fourteen_cases(self):
        validation=self.root/'validation.json';validation.write_text(json.dumps({'stage':'patched','complete':True,'artifacts_unchanged':True,'cases':[]}));proof=self.root/'proof.json';proof.write_text('{}')
        with self.assertRaisesRegex(g.GuardError,'14-case'):self.guard.approve(self.browser,validation,proof)
    def test_temporary_pin_removed_after_failed_update(self):
        self.guard.status=lambda **kw:{'version':'1.0+hw'}
        observed=[]
        def run(command,**kw):
            pin=Path(command[-1].split('=',1)[1]);observed.append(pin);self.assertIn('Pin: version 1.0+hw',pin.read_text());return subprocess.CompletedProcess(command,17)
        with patch.object(g.subprocess,'run',side_effect=run):self.assertEqual(self.guard.upgrade(['not-a-real-update']),17)
        self.assertFalse(observed[0].exists());self.assertFalse((self.prefix/'etc/apt/preferences').exists())
    def full_validation(self):
        # Explicitly synthetic receipts test authorization mechanics, never playback.
        rows=[{'mode':mode,'checks_passed':True,'cleanup_ok':True,'exit':0,'native_direct':True,'expected_libxul_loaded':True,'tracer_pid':'TracerPid: 0','output_hardware_decoder':mode=='hardware','hardware_decoder_names':['synthetic-test-only']} for mode in ['software','hardware']]
        import copy
        cases=[]
        for name in sorted(g.CASES):
            current=copy.deepcopy(rows if not name.endswith('-abba') else [rows[0],rows[1],rows[1],rows[0]])
            cases.append({'name':name,'passed':True,'rows':current})
        value={'stage':'patched','complete':True,'artifacts_unchanged':True,'cases':cases,'artifact_fingerprints':{name:{'sha256':checksum} for name,checksum in self.policy['approved_firefox'][0]['binaries'].items()}}
        path=self.root/'complete-synthetic-validation.json';path.write_text(json.dumps(value));return path,value
    def test_full_validation_approves_exact_payload_directly(self):
        path,_=self.full_validation();self.policy['approved_firefox']=[];self.manifest.write_text(json.dumps(self.policy));self.guard.approve(self.browser,path,None)
        self.assertEqual(self.guard.policy()['approved_firefox'][0]['package_sha256'],g.digest(self.browser))
    def test_wrong_validated_binary_cannot_be_approved(self):
        path,value=self.full_validation();value['artifact_fingerprints']['libxul.so']['sha256']='0'*64;path.write_text(json.dumps(value))
        with self.assertRaisesRegex(g.GuardError,'not the validated artifact'):self.guard.approve(self.browser,path,None)
    def test_proot_run_cannot_be_approved(self):
        path,value=self.full_validation();value['cases'][0]['rows'][0]['tracer_pid']='TracerPid: 123';path.write_text(json.dumps(value))
        with self.assertRaisesRegex(g.GuardError,'untraced native'):self.guard.approve(self.browser,path,None)
    def test_hardware_initialization_without_output_cannot_be_approved(self):
        path,value=self.full_validation()
        for case in value['cases']:
            if case['name']=='h264':case['rows'][1]['output_hardware_decoder']=False
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(g.GuardError,'Actual decoded hardware output'):self.guard.approve(self.browser,path,None)
if __name__=='__main__':unittest.main()
