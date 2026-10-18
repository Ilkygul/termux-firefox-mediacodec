#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Check provenance, evidence and the public-file boundary without building Firefox."""
from pathlib import Path
import ast,hashlib,json,re,subprocess,sys,os
ROOT=Path(__file__).resolve().parents[1]
def public_files():
 for folder,directories,files in os.walk(ROOT):
  directories[:]=[name for name in directories if name not in ('.git','.work','__pycache__')]
  for name in files:yield Path(folder)/name

def main():
 errors=[];manifest=json.loads((ROOT/'sources.json').read_text())
 for group,key in [('firefox','feature_patches'),('native-host','native_host_patches')]:
  for entry in manifest[key]:
   file=ROOT/'patches'/group/entry['name']
   if hashlib.sha256(file.read_bytes()).hexdigest()!=entry['sha256']:errors.append('Patch checksum mismatch: '+str(file.relative_to(ROOT)))
 index=json.loads((ROOT/'evidence/index.json').read_text())
 for entry in index['files']:
  if hashlib.sha256((ROOT/'evidence'/entry['file']).read_bytes()).hexdigest()!=entry['sha256']:errors.append('Evidence checksum mismatch: '+entry['file'])
 original=json.loads((ROOT/'evidence/runtime-original.json').read_text())
 if not original['complete'] or not original['artifacts_unchanged'] or len(original['cases'])!=14 or not all(c['passed'] for c in original['cases']):errors.append('Invalid original runtime evidence')
 selected=[]
 for path in public_files():
  rel=path.relative_to(ROOT)
  if any(part in ('.git','.work','__pycache__') for part in rel.parts) or not path.is_file():continue
  selected.append(path)
  if path.suffix in ('.deb','.xpi','.mp4','.webm','.o','.a','.so') or path.name.startswith(('.env','id_ed25519')) or path.name in ('authorized_keys','known_hosts'):errors.append('Private/build artifact in public tree: '+str(rel))
  data=path.read_bytes()
  if data.startswith(b'\x7fELF') or re.search(rb'^-----BEGIN (?:OPENSSH|RSA|EC) PRIVATE KEY-----$',data,re.M):errors.append('Binary/private-key content: '+str(rel))
  try:text=data.decode()
  except UnicodeDecodeError:errors.append('Unexpected binary file: '+str(rel));continue
  if re.search(r'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})',text):errors.append('Possible credential: '+str(rel))
  if path.suffix=='.py':
   try:ast.parse(text)
   except SyntaxError as error:errors.append(str(rel)+': '+str(error))
  if path.suffix=='.sh':
   result=subprocess.run(['bash','-n',str(path)],capture_output=True,text=True)
   if result.returncode:errors.append(result.stderr)
  if path.suffix=='.md':
   for link in re.findall(r'\]\(([^)]+)\)',text):
    link=link.split('#',1)[0]
    if not link or '://' in link or link.startswith('mailto:'):continue
    if not (path.parent/link).exists():errors.append('Broken local link in '+str(rel)+': '+link)
 if errors:
  print('\n'.join(errors),file=sys.stderr);return 1
 print('Repository checks passed:',len(selected),'public text files; patch/evidence hashes, script syntax, links and publication boundary verified.')
 return 0
if __name__=='__main__':raise SystemExit(main())
