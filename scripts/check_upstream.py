#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Report upstream recipe/release drift; never approve, install or hold a package."""
from pathlib import Path
import argparse,json,sys,urllib.request
ROOT=Path(__file__).resolve().parents[1]
def get(url):
 request=urllib.request.Request(url,headers={'User-Agent':'termux-firefox-mediacodec-maintenance','Accept':'application/json'})
 with urllib.request.urlopen(request,timeout=30) as response:return json.load(response)
def compare(manifest,entries,releases):
 actual={item['name']:item['sha'] for item in entries if item.get('type')=='file'}
 expected=manifest['termux_recipe_tree'];changes=[]
 for name in sorted(set(actual)|set(expected)):
  if actual.get(name)!=expected.get(name):changes.append('Termux recipe file changed: '+name)
 latest=releases.get('LATEST_FIREFOX_VERSION') or releases.get('FIREFOX_LATEST')
 if not latest:raise ValueError('Mozilla release feed has no recognized release field.')
 if latest!=manifest['firefox_version']:changes.append('Mozilla stable release differs: '+latest+' (pinned '+manifest['firefox_version']+')')
 return changes

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
 try:
  manifest=json.loads((ROOT/'sources.json').read_text());entries=get('https://api.github.com/repos/termux/termux-packages/contents/x11-packages/firefox?ref=master');releases=get('https://product-details.mozilla.org/1.0/firefox_versions.json');changes=compare(manifest,entries,releases)
  report={'pinned_firefox':manifest['firefox_version'],'changes':changes,'maintenance_required':bool(changes),'runtime_tested_by_this_check':False}
  if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps(report,indent=2))
  return 1 if changes else 0
 except (OSError,ValueError,KeyError,TypeError) as error:
  print('Upstream status UNKNOWN; do not treat this as an up-to-date result: '+str(error),file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())
