#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Prepare the pinned Firefox source and ordered patches; never install a browser."""
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tarfile,urllib.request
ROOT=Path(__file__).resolve().parents[1]
def digest(path):
 with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def fetch(url,path,expected):
 if path.exists():
  if digest(path)!=expected:raise SystemExit('Existing file checksum mismatch: '+str(path))
  return
 path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix(path.suffix+'.part')
 with urllib.request.urlopen(url,timeout=60) as response,temporary.open('wb') as output:
  shutil.copyfileobj(response,output,1024*1024)
 if digest(temporary)!=expected:raise SystemExit('Download checksum mismatch: '+url)
 os.replace(temporary,path)
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,default=ROOT/'.work/native');p.add_argument('--native',action='store_true');p.add_argument('--baseline',action='store_true');args=p.parse_args()
 manifest=json.loads((ROOT/'sources.json').read_text());work=args.work.resolve();source=work/'source-baseline'
 if source.exists():raise SystemExit('Source directory already exists. Inspect/reuse it; do not apply the patchset twice.')
 work.mkdir(parents=True,exist_ok=True);archive=work/'firefox.source.tar.xz';fetch(manifest['source_url'],archive,manifest['source_sha256'])
 cache=work/'downloaded-patches';official=[]
 for entry in manifest['termux_patches']:
  name=entry['name'];target=cache/name
  fetch('https://raw.githubusercontent.com/termux/termux-packages/'+manifest['termux_revision']+'/x11-packages/firefox/'+name,target,entry['sha256']);official.append(target)
 local=[]
 for group,key in [('native-host','native_host_patches'),('firefox','feature_patches')]:
  if group=='native-host' and not args.native or group=='firefox' and args.baseline:continue
  for entry in manifest[key]:
   path=ROOT/'patches'/group/entry['name']
   if digest(path)!=entry['sha256']:raise SystemExit('Local patch checksum mismatch: '+path.name)
   local.append(path)
 source.mkdir();subprocess.run(['tar','-xJf',str(archive),'--strip-components=1','--no-same-owner','-C',str(source)],check=True)
 prefix=Path(os.environ.get('PREFIX','/data/data/com.termux/files/usr'))
 for path in official+local:
  data=path.read_text().replace('@TERMUX_PREFIX@',str(prefix));subprocess.run(['patch','--batch','--forward','-p1'],cwd=source,input=data,text=True,check=True)
 config=source/'media/ffvpx/config_unix_aarch64.h';config.write_text(re.sub(r'(?m)^(#define (?:CONFIG_LINUX_PERF|HAVE_SYSCTL) )1$',r'\g<1>0',config.read_text()))
 if args.native:
  crate=source/'third_party/rust/glslopt';checksums=crate/'.cargo-checksum.json';values=json.loads(checksums.read_text());name='glsl-optimizer/src/util/os_misc.c';values['files'][name]=digest(crate/name);checksums.write_text(json.dumps(values,separators=(',',':')))
  for name in ['native-build-env.py','native-stage.py','native-mozconfig.cfg']:
   text=(ROOT/'scripts'/name).read_text().replace('/data/data/com.termux/files/usr',str(prefix));(work/name).write_text(text)
  (source/'.mozconfig').write_text((work/'native-mozconfig.cfg').read_text().replace('@BUILD_ROOT@',str(work)))
  tools=work/'native-build-tools/bin';tools.mkdir(parents=True,exist_ok=True)
  for compiler in ['clang','clang++']:
   wrapper=tools/('fold-native-'+compiler);wrapper.write_text('#!'+str(prefix/'bin/sh')+'\nexec '+str(prefix/'bin'/compiler)+' "$@" --target=aarch64-linux-android24\n');wrapper.chmod(0o755)
 state={**manifest,'source':str(source),'custom_decoder_patches_applied':not args.baseline,'native_host_patches_applied':args.native}
 (work/'native-source-state.json').write_text(json.dumps(state,indent=2)+'\n');(source/'.fold-source-prepared.json').write_text(json.dumps(state,indent=2)+'\n')
 print('Source prepared. No build or installation has been started:',source)
if __name__=='__main__':main()
