#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Install the update guard for an ALREADY validated native Firefox installation."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import runpy
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', default=os.environ.get('PREFIX','/data/data/com.termux/files/usr'))
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--update-script',action='append',type=Path,default=[])
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args();prefix=Path(args.prefix).absolute()
    Guard=runpy.run_path(str(ROOT/'scripts/update_guard.py'))['Guard']
    guard=Guard(prefix,args.manifest);state=guard.installed()
    library=prefix/'libexec/firefox-mediacodec/update_guard.py'
    approval=prefix/'var/lib/firefox-mediacodec/approved.json'
    launcher=prefix/'bin/fold-firefox-maintenance'
    hook=prefix/'etc/apt/apt.conf.d/90-firefox-mediacodec'
    python=prefix/'bin/python'
    command=' '.join(shlex.quote(str(s)) for s in [python,library,'--prefix',prefix])
    config='// Native Firefox MediaCodec update protection; no background service.\n'
    config+='DPkg::Pre-Install-Pkgs { "'+command+' apt-hook"; };\n'
    config+='DPkg::Post-Invoke { "'+command+' status"; };\n'
    wrapper='#!'+str(prefix/'bin/sh')+'\nexec '+command+' "$@"\n'
    edits={}
    for path in args.update_script:
        old=path.read_text();plain='pkg upgrade -y';protected=str(launcher)+' protected-upgrade -- pkg upgrade -y'
        if protected in old:continue
        if old.count(plain)!=1:raise SystemExit('Expected exactly one general pkg upgrade in '+str(path))
        edits[path]=(old,old.replace(plain,protected).replace('inclusief Brave,','inclusief native Firefox,'))
    if hook.exists() and 'Native Firefox MediaCodec update protection' not in hook.read_text():raise SystemExit('Unmanaged APT hook already exists; inspect it first.')
    record={'version':state['version'],'targets':[str(p) for p in [library,approval,launcher,hook]],'update_scripts':[str(p) for p in edits],'background_services_added':0,'persistent_holds_added':0}
    if args.dry_run:print(json.dumps(record,indent=2));return
    # Preflight succeeded before touching installed files. No browser/profile is copied.
    files={library:(ROOT/'scripts/update_guard.py').read_text(),approval:args.manifest.read_text(),launcher:wrapper,hook:config}
    for path,text in files.items():
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text);path.chmod(0o600 if path==approval else (0o755 if path==launcher else 0o644))
    for path,(old,new) in edits.items():
        mode=path.stat().st_mode&0o777;path.write_text(new);path.chmod(mode)
        record.setdefault('script_changes',[]).append({'path':str(path),'before_sha256':hashlib.sha256(old.encode()).hexdigest(),'after_sha256':hashlib.sha256(new.encode()).hexdigest()})
    record['installed']=True
    output=prefix/'var/lib/firefox-mediacodec/installation.json';output.write_text(json.dumps(record,indent=2)+'\n');output.chmod(0o600)
    print(json.dumps(record,indent=2))
if __name__=='__main__':main()
