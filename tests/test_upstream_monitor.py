# SPDX-License-Identifier: MPL-2.0
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('monitor',ROOT/'scripts/check_upstream.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class MonitorTests(unittest.TestCase):
 def setUp(self):self.manifest={'firefox_version':'158.0','termux_recipe_tree':{'build.sh':'original','fix.patch':'old'}};self.entries=[{'name':k,'sha':v,'type':'file'} for k,v in self.manifest['termux_recipe_tree'].items()]
 def test_same_recipe_and_release(self):self.assertEqual(m.compare(self.manifest,self.entries,{'LATEST_FIREFOX_VERSION':'158.0'}),[])
 def test_security_release_requires_maintenance(self):self.assertTrue(any('158.0.1' in s for s in m.compare(self.manifest,self.entries,{'LATEST_FIREFOX_VERSION':'158.0.1'})))
 def test_patch_only_change_is_detected(self):self.entries[1]['sha']='new';self.assertIn('Termux recipe file changed: fix.patch',m.compare(self.manifest,self.entries,{'LATEST_FIREFOX_VERSION':'158.0'}))
 def test_added_patch_is_detected(self):self.entries.append({'name':'new.patch','sha':'new','type':'file'});self.assertIn('Termux recipe file changed: new.patch',m.compare(self.manifest,self.entries,{'LATEST_FIREFOX_VERSION':'158.0'}))
 def test_unknown_release_feed_is_not_green(self):
  with self.assertRaises(ValueError):m.compare(self.manifest,self.entries,{})
if __name__=='__main__':unittest.main()
