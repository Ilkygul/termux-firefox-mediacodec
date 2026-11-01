#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run the isolated native 14-case matrix; never use the normal browser profile."""
from pathlib import Path
import argparse,hashlib,json,os,signal,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[1]
CASES=[('h264','h264.mp4',{}),('h264-4k','h264-4k.mp4',{}),('vp9','vp9-continuous.webm',{}),('av1-fallback','av1.webm',{'PROBE_EXPECT_SOFTWARE':'1'}),('10bit-fallback','h264-10bit.mp4',{'PROBE_EXPECT_SOFTWARE':'1'}),('streaming-aac','h264-high-audio.mp4',{'PROBE_MSE':'1'}),('h264-selection','h264.mp4',{'PROBE_DECODER_TRACE':'1'}),('vp9-selection','vp9-continuous.webm',{'PROBE_DECODER_TRACE':'1'}),('hardware-disabled','h264.mp4',{'PROBE_DISABLE_HARDWARE':'1','PROBE_DECODER_TRACE':'1'}),('concurrent-resize','h264-high-long.mp4',{'PROBE_LONG':'1'}),('h264-4k-pacing','h264-4k.mp4',{'PROBE_PACING':'1'}),('vp9-pacing','vp9-continuous.webm',{'PROBE_PACING':'1'}),('h264-4k-abba','h264-4k.mp4',{'PROBE_ORDER':'software,hardware,hardware,software'}),('vp9-abba','vp9-continuous.webm',{'PROBE_ORDER':'software,hardware,hardware,software'})]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,default=Path(os.environ.get('PREFIX','/data/data/com.termux/files/usr'))/'lib/firefox/firefox');p.add_argument('--work',type=Path,default=ROOT/'.work/runtime');p.add_argument('--list',action='store_true');args=p.parse_args()
 if args.list:print(json.dumps(CASES,indent=2));return 0
 prefix=Path(os.environ.get('PREFIX','/data/data/com.termux/files/usr'));tracer=next(l.split(':',1)[1].strip() for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('TracerPid:'))
 if not Path(sys.executable).resolve().is_relative_to(prefix) or tracer!='0':raise SystemExit('Use native Termux Python outside PRoot.')
 binary=args.binary.resolve();header=binary.open('rb').read(20)
 if header[:5]!=b'\x7fELF\x02' or int.from_bytes(header[18:20],'little')!=183:raise SystemExit('Expected native AArch64 ELF Firefox.')
 work=args.work.resolve();work.mkdir(parents=True,exist_ok=True);output=work/('validation-'+str(time.time_ns()));output.mkdir()
 for _,name,_ in CASES:
  if not (work/'test-media'/name).exists():raise SystemExit('Generate fixtures first: missing '+name)
 def fingerprints():
  result={}
  for name in ['firefox','libxul.so']:
   target=binary if name=='firefox' else binary.parent/name
   with target.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
   result[name]={'path':str(target),'sha256':checksum,'bytes':target.stat().st_size}
  return result
 before=fingerprints();summary={'stage':'patched','binary':str(binary),'tracer_pid':tracer,'complete':False,'cases':[],'artifact_fingerprints':before}
 env={k:v for k,v in os.environ.items() if not k.startswith('PROBE_') and k not in ('LD_PRELOAD','LD_LIBRARY_PATH')};env.update(PROBE_NATIVE_DECODER='1',PROBE_REQUIRE_SELECTION_LOG='1',PROBE_FIREFOX_EXE=str(binary),FOLD_FIREFOX_TEST_ROOT=str(work))
 for name,media,options in CASES:
  current=env.copy();current.update(PROBE_ORDER='software,hardware',PROBE_MEDIA=media);current.update(options);marker=os.urandom(12).hex();current['FOLD_VALIDATION_RUN_ID']=marker;entry={'name':name,'media':media,'options':options,'passed':False};print('START',name,flush=True)
  try:
   run=subprocess.run([sys.executable,str(ROOT/'scripts/browser_probe.py')],env=current,capture_output=True,text=True,timeout=600);(output/(name+'.stdout')).write_text(run.stdout);(output/(name+'.stderr')).write_text(run.stderr);rows=[json.loads(l) for l in run.stdout.splitlines() if l.startswith('{')];entry.update(returncode=run.returncode,rows=rows);entry['passed']=run.returncode==0 and [r.get('mode') for r in rows]==current['PROBE_ORDER'].split(',') and all(r.get('checks_passed') and r.get('cleanup_ok') and r.get('exit')==0 for r in rows)
  except (OSError,ValueError,subprocess.TimeoutExpired) as exc:entry['error']=str(exc)
  finally:
   # A timeout must not strand the owned browser. Match only our unique marker.
   owned=[]
   for proc in Path('/proc').iterdir():
    try:
     if proc.name.isdigit() and os.path.samefile(os.readlink(proc/'exe'),binary) and ('FOLD_VALIDATION_RUN_ID='+marker).encode()+b'\0' in (proc/'environ').read_bytes():owned.append(int(proc.name))
    except OSError:pass
   if owned:
    entry['passed']=False;entry['leftover_owned_pids']=owned
    for pid in owned:
     try:os.kill(pid,signal.SIGTERM)
     except ProcessLookupError:pass
  summary['cases'].append(entry);(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('RESULT',name,entry['passed'],flush=True)
  if not entry['passed']:print('Validation stopped:',output);return 1
 summary['artifacts_unchanged']=fingerprints()==before;summary['complete']=summary['artifacts_unchanged'];(output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print('Validation result:',output/'summary.json');return 0 if summary['complete'] else 1
if __name__=='__main__':raise SystemExit(main())
