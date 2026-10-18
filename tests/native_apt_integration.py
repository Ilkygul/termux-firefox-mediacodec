#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Exercise real native APT hooks against an isolated status file and refusing dpkg stub.
Never installs a test package into the live environment.
"""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
P=Path(os.environ.get('PREFIX','/data/data/com.termux/files/usr'))
def main():
    if not Path(sys.executable).resolve().is_relative_to(P):raise SystemExit('Use native Termux Python.')
    tracer=next(l.split(':',1)[1].strip() for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('TracerPid:'))
    if tracer!='0':raise SystemExit('Run outside PRoot.')
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    live=P/'var/lib/dpkg/status';before=sha(live);cases=[]
    with tempfile.TemporaryDirectory(prefix='mediacodec-apt-test-',dir=P/'tmp') as directory:
        work=Path(directory);status=work/'status';status.write_text('');archives=work/'archives';archives.mkdir();(archives/'partial').mkdir();marker=work/'dpkg-mutation-attempt';stub=work/'dpkg-stub'
        stub.write_text('#!'+str(P/'bin/python')+'\n'+'''import os,sys
from pathlib import Path
args=sys.argv[1:]
readonly=['--version','--print-architecture','--print-foreign-architectures','--get-selections']
if len(args)==1 and (args[0] in readonly or args[0].startswith('--assert-')):
 os.execv('''+repr(str(P/'bin/dpkg'))+''',['dpkg',*args])
Path('''+repr(str(marker))+''').write_text(repr(args))
print('DPKG_STUB_REFUSED_MUTATION',file=sys.stderr)
sys.exit(125)
''');stub.chmod(0o755)
        config=work/'apt.conf';guard=ROOT/'scripts/update_guard.py';manifest=ROOT/'examples/tested-device-approval.json'
        cmd=f'{P}/bin/python {guard} --prefix {P} --manifest {manifest} apt-hook'
        config.write_text('DPkg::Pre-Install-Pkgs { "'+cmd+'"; };\n')
        for name,blocked in [('firefox',True),('ffmpeg',True),('mediacodec-guard-fixture',False)]:
            tree=work/(name+'-tree');control=tree/'DEBIAN';control.mkdir(parents=True);control.chmod(0o755)
            (control/'control').write_text(f'Package: {name}\nVersion: 999.0\nArchitecture: aarch64\nMaintainer: Guard test <test@example.invalid>\nDescription: Synthetic APT hook test, never installed\n')
            package=work/(name+'.deb');subprocess.run([str(P/'bin/dpkg-deb'),'--build',str(tree),str(package)],capture_output=True,check=True)
            if marker.exists():marker.unlink()
            command=[str(P/'bin/apt-get'),'-c',str(config),'-y','-o','Acquire::http::Proxy=http://127.0.0.1:9','-o','Acquire::https::Proxy=http://127.0.0.1:9','-o','Dir::State::status='+str(status),'-o','Dir::Cache::archives='+str(archives),'-o','Dir::Bin::dpkg='+str(stub),'-o','Debug::NoLocking=1','-o','DPkg::ConfigurePending=false','install',str(package)]
            result=subprocess.run(command,capture_output=True,text=True,timeout=45)
            text=result.stdout+result.stderr
            reached=marker.exists();guard_message='Firefox MediaCodec guard:' in text
            passed=result.returncode!=0 and ((blocked and guard_message and not reached) or (not blocked and reached and 'DPKG_STUB_REFUSED_MUTATION' in text))
            cases.append({'package':name,'expected_guard_block':blocked,'guard_message':guard_message,'dpkg_stub_reached':reached,'exit':result.returncode,'passed':passed})
            if not passed:print(text,file=sys.stderr)
    report={'tracer_pid':tracer,'real_native_apt':True,'isolated_dpkg_status':True,'refusing_dpkg_stub':True,'live_dpkg_status_unchanged':sha(live)==before,'cases':cases,'passed':all(c['passed'] for c in cases) and sha(live)==before}
    print(json.dumps(report,indent=2));return 0 if report['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
