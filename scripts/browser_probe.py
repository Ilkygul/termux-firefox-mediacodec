# SPDX-License-Identifier: MPL-2.0
"""Isolated native Firefox runtime probe; no normal profile is copied or opened."""
from pathlib import Path
import os,subprocess,time,json,http.server,threading,signal,socket,struct,base64,re,shutil
class CDP:
 def __init__(self,url):
  from urllib.parse import urlsplit
  u=urlsplit(url);self.s=socket.create_connection((u.hostname,u.port),timeout=10);self.s.settimeout(60);self.id=0;self.events=[]
  key=base64.b64encode(os.urandom(16)).decode();self.s.sendall(f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode());h=b''
  while not h.endswith(b'\r\n\r\n'):h+=self.s.recv(1)
  assert b'101' in h.split(b'\r\n')[0]
 def read(self,n):
  data=b''
  while len(data)<n:
   chunk=self.s.recv(n-len(data))
   if not chunk:raise ConnectionError('Browser closed')
   data+=chunk
  return data
 def call(self,method,params=None):
  self.id+=1;data=json.dumps({'id':self.id,'method':method,'params':params or {}}).encode();mask=os.urandom(4);n=len(data);header=b'\x81'+(bytes([128|n]) if n<126 else b'\xfe'+struct.pack('!H',n) if n<65536 else b'\xff'+struct.pack('!Q',n));self.s.sendall(header+mask+bytes(v^mask[i%4] for i,v in enumerate(data)))
  while True:
   a,b=self.read(2);n=b&127
   if n==126:n=struct.unpack('!H',self.read(2))[0]
   elif n==127:n=struct.unpack('!Q',self.read(8))[0]
   mask=self.read(4) if b&128 else None;raw=self.read(n)
   if mask:raw=bytes(v^mask[i%4] for i,v in enumerate(raw))
   if a&15==8:raise ConnectionError('Browser closed')
   obj=json.loads(raw)
   if obj.get('id')==self.id:return obj
   self.events.append(obj)
 def close(self):self.s.close()

B=Path(os.environ.get('FOLD_FIREFOX_TEST_ROOT',str(Path.cwd()/'.work/runtime'))).resolve();B.mkdir(parents=True,exist_ok=True);P=Path(os.environ.get('PREFIX','/data/data/com.termux/files/usr'));H=Path.home()
import sys
if not Path(sys.executable).resolve().is_relative_to(P):raise SystemExit('Use native Termux Python.')
if next(l.split(':',1)[1].strip() for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('TracerPid:'))!='0':raise SystemExit('Run outside PRoot/tracing.')
ENV=os.environ.copy()
for k in ['LD_PRELOAD','LD_LIBRARY_PATH']:ENV.pop(k,None)
ENV.update(DISPLAY=':0',GDK_BACKEND='x11',GALLIUM_DRIVER='zink',MESA_LOADER_DRIVER_OVERRIDE='zink',ZINK_DESCRIPTORS='lazy',MOZ_USE_XINPUT2='1')
for p in Path('/proc').iterdir():
 try:
  if (p/'comm').read_text().strip()=='xfce4-panel':
   e=dict(x.split(b'=',1) for x in (p/'environ').read_bytes().split(b'\0') if b'=' in x)
   if b'DBUS_SESSION_BUS_ADDRESS' in e:ENV['DBUS_SESSION_BUS_ADDRESS']=e[b'DBUS_SESSION_BUS_ADDRESS'].decode()
   break
 except OSError:pass
class Handler(http.server.SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(B/'test-media'),**kw)
 def log_message(self,*a):pass
http=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=http.serve_forever,daemon=True).start()
(B/'test-media/index.html').write_text('<!doctype html><title>Firefox decoder test</title><style>body{background:#182030;color:white}video{width:640px}</style><video id="v" muted loop playsinline></video>')
def value(x):
 if x.get('type')=='object':return {k:value(v) for k,v in x.get('value',[])}
 if x.get('type')=='array':return [value(v) for v in x.get('value',[])]
 return x.get('value')
def owned_browser_pids(tag):
 result=[]
 for p in Path('/proc').iterdir():
  try:
   if not p.name.isdigit():continue
   exe=os.readlink(p/'exe')
   if not (exe.startswith(str(firefox.resolve().parent)) or exe.startswith(str(P/'lib/firefox'))):continue
   if (p/'stat').read_text().rsplit(')',1)[1].split()[0]=='Z':continue
   marker=('FOLD_BROWSER_PROBE_ID='+tag).encode()+b'\0'
   if marker in (p/'environ').read_bytes():result.append(int(p.name))
  except (OSError,ValueError):pass
 return result
def ticks(root):
 all={}
 for p in Path('/proc').iterdir():
  try:
   if not p.name.isdigit():continue
   s=(p/'stat').read_text().rsplit(')',1)[1].split();all[int(p.name)]=(int(s[1]),int(s[11])+int(s[12]))
  except (OSError,ValueError):pass
 ids={root}
 while True:
  n=len(ids);ids.update(k for k,v in all.items() if v[0] in ids)
  if len(ids)==n:break
 return {pid:all[pid][1] for pid in ids if pid in all}
native=True;firefox=Path(os.environ.get('PROBE_FIREFOX_EXE',str(P/'bin/firefox')))
media=os.environ.get('PROBE_MEDIA','h264.mp4');order=os.environ.get('PROBE_ORDER','software,hardware').split(',')
rows=[]
try:
 for mode in order:
  profile=B/('profile-'+mode+('-native' if native else ''));profile.mkdir(exist_ok=True)
  prefs={'browser.shell.checkDefaultBrowser':False,'browser.startup.page':0,'browser.startup.homepage':'about:blank','browser.newtabpage.enabled':False,'browser.aboutwelcome.enabled':False,'browser.startup.firstrunSkipsHomepage':True,'browser.newtabpage.activity-stream.telemetry':False,'datareporting.policy.dataSubmissionEnabled':False,'toolkit.telemetry.enabled':False,'media.autoplay.default':0,'browser.sessionstore.resume_from_crash':False,'browser.bookmarks.max_backups':0,'browser.backup.enabled':False}
  prefs['media.hardware-video-decoding.enabled']=not bool(os.environ.get('PROBE_DISABLE_HARDWARE'))
  if os.environ.get('PROBE_SYSTEM_CODECS') and not native:prefs['media.ffvpx.enabled']=(mode!='hardware')
  if native:
   prefs['media.ffmpeg.preferred']=(mode=='hardware')
   prefs['media.ffmpeg.mediacodec.enabled']=(mode=='hardware')
  (profile/'user.js').write_text('\n'.join('user_pref('+json.dumps(k)+','+json.dumps(v)+');' for k,v in prefs.items()))
  env=ENV.copy();probe_tag=os.urandom(12).hex();env["FOLD_BROWSER_PROBE_ID"]=probe_tag
  if mode=='hardware' and not native:env['LD_LIBRARY_PATH']=str(B/'private-codec')
  if native:env['MOZ_LOG']='FFmpegLib:3,MediaFormatReader:'+('4' if os.environ.get('PROBE_DECODER_TRACE') else '3')
  log=B/('firefox-'+mode+'.log');proc=None;b=None;row={'mode':mode,'media':media,'native_direct':native,'requires_output_selection_log':bool(os.environ.get('PROBE_REQUIRE_SELECTION_LOG')),'hardware_disabled_by_pref':bool(os.environ.get('PROBE_DISABLE_HARDWARE')),'requested_executable':str(firefox)}
  try:
   with log.open('wb') as f:proc=subprocess.Popen([str(firefox),'--no-remote','--new-instance','--profile',str(profile),'--remote-debugging-port=0','--width','900','--height','650','about:blank'],env=env,stdout=f,stderr=f,start_new_session=True)
   deadline=time.monotonic()+25;match=None
   while time.monotonic()<deadline:
    match=re.search(r'WebDriver BiDi listening on (ws://[^\s]+)',log.read_text(errors='replace'))
    if match:break
    if proc.poll() is not None:raise RuntimeError('browser exited '+str(proc.returncode))
    time.sleep(.2)
   if not match:raise RuntimeError('no BiDi endpoint')
   b=CDP(match.group(1).rstrip('/')+'/session');session=b.call('session.new',{'capabilities':{}})
   context=b.call('browsingContext.getTree',{})['result']['contexts'][0]['context']
   r=b.call('browsingContext.navigate',{'context':context,'url':os.environ.get('PROBE_PAGE_URL','http://127.0.0.1:'+str(http.server_port)+'/index.html'),'wait':'complete'})
   if r.get('type')=='error':raise RuntimeError(str(r))
   def evaluate(expr):
    r=b.call('script.evaluate',{'expression':expr,'target':{'context':context},'awaitPromise':True,'resultOwnership':'none'})
    if r.get('type')=='error' or r.get('result',{}).get('type')=='exception':raise RuntimeError(str(r)[:1200])
    return value(r['result']['result'])
   if os.environ.get('PROBE_PAGE_URL'):
    evaluate("document.body.innerHTML='<video id=\"v\" muted loop playsinline></video>'")
    row['document_origin']=evaluate("({origin:location.origin,secure:isSecureContext})")
   setup="v.src="+json.dumps(os.environ.get('PROBE_MEDIA_URL',media))+";"
   if os.environ.get('PROBE_MSE'):
    setup="let ms=new MediaSource();let opened=new Promise(r=>ms.addEventListener('sourceopen',r,{once:true}));v.src=URL.createObjectURL(ms);await opened;let mime='video/mp4; codecs=\"avc1.640028,mp4a.40.2\"';if(!MediaSource.isTypeSupported(mime))throw Error('MSE type unavailable');let sb=ms.addSourceBuffer(mime),bytes=await (await fetch("+json.dumps(media)+")).arrayBuffer();let updated=new Promise((r,j)=>{sb.addEventListener('updateend',r,{once:true});sb.addEventListener('error',j,{once:true})});sb.appendBuffer(bytes);await updated;ms.endOfStream();"
   row['mse']=bool(os.environ.get('PROBE_MSE'))
   row['start']=evaluate("(async()=>{let v=document.getElementById('v');"+setup+"await Promise.race([v.play(),new Promise((_,r)=>setTimeout(()=>r(Error('play timeout')),10000))]);await new Promise(r=>setTimeout(r,2000));return {ready:v.readyState,width:v.videoWidth,audio:v.mozHasAudio}})()")
   row['pacing_requested']=bool(os.environ.get('PROBE_PACING'))
   first=ticks(proc.pid);start=time.monotonic()
   row['playback']=evaluate("(async()=>{let v=document.getElementById('v'),a=v.getVideoPlaybackQuality();let intervals=[],previous=null,callback=null,collect=(t)=>{if(previous!==null)intervals.push(t-previous);previous=t;callback=v.requestVideoFrameCallback(collect)};if("+json.dumps(bool(os.environ.get('PROBE_PACING')))+")callback=v.requestVideoFrameCallback(collect);await new Promise(r=>setTimeout(r,6000));if(callback!==null)v.cancelVideoFrameCallback(callback);intervals.sort((a,b)=>a-b);let pacing=intervals.length?{samples:intervals.length,medianMs:intervals[Math.floor(intervals.length/2)],p95Ms:intervals[Math.min(intervals.length-1,Math.ceil(intervals.length*.95)-1)],maxMs:intervals[intervals.length-1]}:null;let q=v.getVideoPlaybackQuality(),c=document.createElement('canvas');c.width=64;c.height=36;let g=c.getContext('2d');g.drawImage(v,0,0,64,36);let d=g.getImageData(0,0,64,36).data,lo=765,hi=0;for(let i=0;i<d.length;i+=4){let x=d[i]+d[i+1]+d[i+2];lo=Math.min(lo,x);hi=Math.max(hi,x)}return {width:v.videoWidth,height:v.videoHeight,frames:q.totalVideoFrames-a.totalVideoFrames,dropped:q.droppedVideoFrames-a.droppedVideoFrames,pixelRange:hi-lo,error:v.error&&v.error.code,time:v.currentTime,frameCallbackTiming:pacing}})()")
   elapsed=time.monotonic()-start;last=ticks(proc.pid);
   pss=0
   for pid in last:
    try:pss+=next(int(l.split()[1]) for l in Path('/proc/'+str(pid)+'/smaps_rollup').read_text().splitlines() if l.startswith('Pss:'))
    except (OSError,StopIteration):pass
   row['pss_mib']=pss/1024;row['processes']=len(last);
   row['cpu_one_core_pct']=100*sum(t-first.get(pid,t) for pid,t in last.items())/os.sysconf('SC_CLK_TCK')/elapsed
   loaded=set()
   for pid in last:
    try:
     for line in Path('/proc/'+str(pid)+'/maps').read_text().splitlines():
      parts=line.split(None,5)
      if len(parts)==6 and parts[5].startswith('/'):
       path=parts[5]
       name=Path(path.removesuffix(' (deleted)')).name
       if name=='libxul.so' or name=='libbinder_ndk.so' or name.startswith(('libavcodec.so','libmozavcodec.so','libfoldavcodec.so')):loaded.add(path)
    except OSError:pass
   row['loaded_decoder_libraries']=sorted(loaded)
   expected_libs=[firefox.parent/'libxul.so',firefox.resolve().parent/'libxul.so']
   row['expected_libxul']=next((str(path.resolve()) for path in expected_libs if path.is_file()),None)
   row['expected_libxul_loaded']=False
   if row['expected_libxul']:
    for path in loaded:
     try:
      if Path(path).name=='libxul.so' and os.path.samefile(row['expected_libxul'],path):row['expected_libxul_loaded']=True
     except OSError:pass
   row['seek']=evaluate("(async()=>{let v=document.getElementById('v');v.currentTime=1;await new Promise(r=>setTimeout(r,1500));return {time:v.currentTime,ready:v.readyState,error:v.error&&v.error.code}})()")
   row['pause_resume']=evaluate("(async()=>{let v=document.getElementById('v');v.pause();let a=v.currentTime;await new Promise(r=>setTimeout(r,300));let stationary=Math.abs(v.currentTime-a)<0.05;await v.play();await new Promise(r=>setTimeout(r,700));return {stationary,advanced:v.currentTime>a+0.3}})()")
   if os.environ.get('PROBE_LONG'):
    row['concurrent']=evaluate("(async()=>{let v=document.getElementById('v');let w=document.createElement('video');w.id='second';w.muted=true;w.src="+json.dumps(media)+";w.style.width='320px';document.body.appendChild(w);await w.play();await new Promise(r=>setTimeout(r,2000));let a=v.getVideoPlaybackQuality(),b=w.getVideoPlaybackQuality();await new Promise(r=>setTimeout(r,30000));let c=v.getVideoPlaybackQuality(),d=w.getVideoPlaybackQuality();let result={firstFrames:c.totalVideoFrames-a.totalVideoFrames,firstDropped:c.droppedVideoFrames-a.droppedVideoFrames,secondFrames:d.totalVideoFrames-b.totalVideoFrames,secondDropped:d.droppedVideoFrames-b.droppedVideoFrames,firstError:v.error&&v.error.code,secondError:w.error&&w.error.code};w.pause();w.removeAttribute('src');w.load();w.remove();let t=v.currentTime;await new Promise(r=>setTimeout(r,1000));result.remainingAdvanced=v.currentTime>t+0.5;return result})()")
    row['viewport'] = []
    windows=subprocess.run(['xdotool','search','--onlyvisible','--pid',str(proc.pid)],env=env,capture_output=True,text=True,timeout=5)
    ids=windows.stdout.split()
    if not ids:raise RuntimeError('No owned X11 test window found')
    for width,height in [(720,1200),(1200,720),(1600,1900)]:
     subprocess.run(['xdotool','windowsize',ids[0],str(width),str(height)],env=env,capture_output=True,text=True,check=True,timeout=5)
     time.sleep(.5)
     row['viewport'].append({'requested_physical_width':width,'requested_physical_height':height,'state':evaluate("({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,time:document.getElementById('v').currentTime,ready:document.getElementById('v').readyState})")})
    if mode=='hardware':
     shot=b.call('browsingContext.captureScreenshot',{'context':context,'origin':'viewport'})
     if shot.get('type')=='success':(B/'hardware-video-test.png').write_bytes(base64.b64decode(shot['result']['data']))
   decoder_log=log.read_text(errors='replace')
   row['hardware_decoder_names']=sorted(set(re.findall(r'MediaCodec started successfully: codec = (c2\.qti\.[^,\s]+)',decoder_log)))
   row['codec_active']=bool(row['hardware_decoder_names']) if native else 'fold-native-hw: active' in decoder_log
   if native:
    row['decoder_outputs']=re.findall(r'Termux video output: description="([^"\n]*)", hw="([^"\n]*)"',decoder_log)
    row['output_hardware_decoder']=bool(row['decoder_outputs'] and 'MediaCodec NDK video decoder (system FFmpeg)' in row['decoder_outputs'][-1][0] and row['decoder_outputs'][-1][1] in ('true','1'))
   if native and os.environ.get('PROBE_DECODER_TRACE'):
    row['decoder_initializations']=re.findall(r'Decoder init finished for video codec: "([^"\n]*)", description: "([^"\n]*)", process: "([^"\n]*)", hw: "([^"\n]*)"',decoder_log)
    row['initialization_reported_hardware']=bool(row['decoder_initializations'] and 'MediaCodec NDK video decoder (system FFmpeg)' in row['decoder_initializations'][-1][1] and row['decoder_initializations'][-1][3] in ('true','1'))
   row['actual_executable']=os.readlink('/proc/'+str(proc.pid)+'/exe')
   row['tracer_pid']=next(x for x in Path('/proc/'+str(proc.pid)+'/status').read_text().splitlines() if x.startswith('TracerPid:'))
   row['checks_passed']=(row['playback']['frames']>=int(os.environ.get('PROBE_MIN_FRAMES','170')) and row['playback']['dropped']==0 and row['playback']['pixelRange']>100 and row['playback']['error'] is None and row['seek']['ready']==4 and row['seek']['time']>1.3 and row['pause_resume']['stationary'] and row['pause_resume']['advanced'] and (row['codec_active']==(mode=='hardware' and not (os.environ.get('PROBE_EXPECT_SOFTWARE') or os.environ.get('PROBE_DISABLE_HARDWARE')))))
   row['checks_passed']=row['checks_passed'] and row['expected_libxul_loaded']
   if row['mse']:row['checks_passed']=row['checks_passed'] and row['start'].get('audio') is True
   if row['pacing_requested']:
    row['checks_passed']=row['checks_passed'] and bool(row['playback'].get('frameCallbackTiming') and row['playback']['frameCallbackTiming']['samples']>0)
   if native and os.environ.get('PROBE_REQUIRE_SELECTION_LOG'):
    row['checks_passed']=row['checks_passed'] and bool(row['decoder_outputs']) and row['output_hardware_decoder']==(mode=='hardware' and not (os.environ.get('PROBE_EXPECT_SOFTWARE') or os.environ.get('PROBE_DISABLE_HARDWARE')))
   if os.environ.get('PROBE_LONG'):
    c=row.get('concurrent',{})
    row['checks_passed']=row['checks_passed'] and c.get('firstFrames',0)>850 and c.get('secondFrames',0)>850 and c.get('firstDropped')==0 and c.get('secondDropped')==0 and c.get('remainingAdvanced') and len(row['viewport'])==3 and all(x['state']['ready']==4 for x in row['viewport'])
   try:b.call('browser.close',{})
   except ConnectionError:pass
   proc.wait(timeout=12);row['exit']=proc.returncode
  except Exception as e:row['error']=str(e)
  finally:
   if b:
    try:b.close()
    except Exception:pass
   if proc and proc.poll() is None:
    proc.terminate()
    try:proc.wait(timeout=8)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
   until=time.monotonic()+5;left=owned_browser_pids(probe_tag)
   while left and time.monotonic()<until:
    time.sleep(.2);left=owned_browser_pids(probe_tag)
   row['leftover_owned_pids']=left;row['cleanup_ok']=not left
   if left:
    row['checks_passed']=False
    for pid in left:
     try:os.kill(pid,signal.SIGTERM)
     except ProcessLookupError:pass
   row['log_tail']=log.read_text(errors='replace')[-2000:];rows.append(row);print(json.dumps(row),flush=True);(B/('firefox-browser-'+media+('-native' if native else '')+('-mse' if os.environ.get('PROBE_MSE') else '')+('-long' if os.environ.get('PROBE_LONG') else '')+('-disabled-hw' if os.environ.get('PROBE_DISABLE_HARDWARE') else '')+('-decoder-trace' if os.environ.get('PROBE_DECODER_TRACE') else '')+('-pacing' if os.environ.get('PROBE_PACING') else '')+'-results.json')).write_text(json.dumps(rows,indent=2))
finally:http.shutdown();http.server_close()
