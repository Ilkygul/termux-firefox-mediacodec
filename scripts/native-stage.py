#!/data/data/com.termux/files/usr/bin/python
# SPDX-License-Identifier: MPL-2.0
"""Run a native build stage inside the task directory; never installs Firefox."""
from pathlib import Path
import os,sys,subprocess,time,runpy,json,signal,argparse
B=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('stage',nargs='?',default='configure',choices=['configure','build'])
parser.add_argument('--jobs',type=int,choices=range(1,9),default=1)
parser.add_argument('--full-power',action='store_true',help='Use all available CPUs at normal priority; retry with fewer jobs only on memory pressure')
options=parser.parse_args();stage=options.stage
env=runpy.run_path(str(B/'native-build-env.py'))['build_env']()
if stage=='build':
 env['FOLD_NATIVE_BUILD_JOBS']=str(options.jobs)
 buildid=B/'obj-native/buildid.h'
 if buildid.exists():env['MOZ_BUILD_DATE']=buildid.read_text().split()[-1]
args=['python',str(B/'source-baseline/mach'),stage]
if stage=='build':
 args+=['-j'+str(options.jobs)]
 if options.full_power:args+=['--priority','normal']
def cpu_frequency(cpu):
 try:return int(Path(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/cpuinfo_max_freq').read_text())
 except (OSError,ValueError):return 0
available_cpus=sorted(os.sched_getaffinity(0),key=lambda cpu:(-cpu_frequency(cpu),cpu))
cpus=available_cpus if options.full_power else available_cpus[:2]
def limits():
 if not options.full_power:os.nice(10)
 os.sched_setaffinity(0,cpus)
minimum_memory_kib=(512 if stage=='configure' else (1024 if options.full_power else 1536))*1024
resume_memory_kib=(768 if stage=='configure' else 2048)*1024
number=1
while (B/f'native-{stage}-{number}.log').exists():number+=1
log=B/f'native-{stage}-{number}.log'
started=time.monotonic();proc=None;paused=False
def stop_stage(signum,frame):
 raise SystemExit(128+signum)
for signum in (signal.SIGTERM,signal.SIGINT,signal.SIGHUP):signal.signal(signum,stop_stage)
try:
 with log.open('wb') as f:
  proc=subprocess.Popen(args,cwd=B/'source-baseline',env=env,stdout=f,stderr=f,start_new_session=True,preexec_fn=limits)
  state={'pid':proc.pid,'stage':stage,'log':str(log),'cpus':cpus,'build_jobs':options.jobs if stage=='build' else None,'status':'running','full_power':options.full_power,'controller_pid':os.getpid(),'started_epoch':time.time()}
  (B/'native-stage-current.json').write_text(json.dumps(state,indent=2))
  print(json.dumps(state),flush=True)
  while proc.poll() is None:
   time.sleep(2 if options.full_power else 10)
   if proc.poll() is not None:break
   memory=next((int(l.split()[1]) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith('MemAvailable:')),None)
   try:
    readings=json.loads(Path('/data/data/com.termux/files/home/.config/fold8/widget/metrics.json').read_text())
    fresh=time.time()-readings.get('timestamp',0)<45
    temp=readings.get('cpu_temp') if fresh else None
    busy=readings.get('cpu') if fresh else None
   except (OSError,ValueError):temp=busy=None
   if options.full_power and memory is not None and memory<minimum_memory_kib:
    state['resource_restart']='Available memory below 1 GiB; preserve objects and retry with fewer jobs'
    (B/'native-stage-current.json').write_text(json.dumps(state,indent=2))
    raise SystemExit(75)
   pressured=(memory is not None and memory<minimum_memory_kib) or (not options.full_power and ((temp is not None and temp>=80) or (busy is not None and busy>=85)))
   recovered=(memory is None or memory>resume_memory_kib) and (temp is None or temp<70) and (busy is None or busy<65)
   if not paused and pressured:
    os.killpg(proc.pid,signal.SIGSTOP);paused=True
    state['resource_pause']=True;(B/'native-stage-current.json').write_text(json.dumps(state,indent=2))
   elif paused and recovered:
    os.killpg(proc.pid,signal.SIGCONT);paused=False
    state['resource_pause']=False;(B/'native-stage-current.json').write_text(json.dumps(state,indent=2))
   print(json.dumps({'pid':proc.pid,'elapsed_seconds':round(time.monotonic()-started),'log_bytes':log.stat().st_size,'mem_available_mib':round(memory/1024) if memory else None}),flush=True)
  state.update(status='finished',returncode=proc.returncode,elapsed_seconds=time.monotonic()-started)
  (B/'native-stage-current.json').write_text(json.dumps(state,indent=2))
 print('STAGE_RESULT',json.dumps(state),flush=True)
 print(log.read_text(errors='replace')[-6500:],flush=True)
 raise SystemExit(proc.returncode)
finally:
 if proc and proc.poll() is None:
  if paused:os.killpg(proc.pid,signal.SIGCONT)
  os.killpg(proc.pid,signal.SIGTERM)
  try:proc.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
  state.update(status='stopped',returncode=proc.returncode,elapsed_seconds=time.monotonic()-started)
  (B/'native-stage-current.json').write_text(json.dumps(state,indent=2))
