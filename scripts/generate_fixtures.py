#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Generate synthetic clips for runtime tests, using one encoding thread."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
def main():
 try:os.nice(10)
 except OSError:pass
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,default=ROOT/'.work/runtime');args=p.parse_args();media=args.work.resolve()/'test-media';media.mkdir(parents=True,exist_ok=True);ffmpeg=shutil.which('ffmpeg');records=[]
 if not ffmpeg:raise SystemExit('ffmpeg is required.')
 def run(name,options):
  output=media/name
  if output.exists():raise SystemExit('Fixture exists; remove your disposable test-media directory explicitly before regenerating: '+str(output))
  command=[ffmpeg,'-hide_banner','-loglevel','error','-nostdin','-filter_threads','1',*options,str(output)];subprocess.run(command,check=True)
  with output.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
  records.append({'name':name,'command':command,'sha256':checksum,'bytes':output.stat().st_size})
 def video(size,duration='12'):return ['-f','lavfi','-i',f'testsrc2=size={size}:rate=30','-t',duration]
 common=['-threads','1','-c:v','libx264','-preset','ultrafast','-crf','28']
 run('h264.mp4',video('1920x1080')+common+['-profile:v','baseline','-pix_fmt','yuv420p','-movflags','+faststart'])
 run('h264-4k.mp4',video('3840x2160')+common+['-profile:v','baseline','-pix_fmt','yuv420p','-movflags','+faststart'])
 run('vp9.webm',video('1920x1080','6')+['-threads','1','-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8','-b:v','2M','-pix_fmt','yuv420p'])
 run('vp9-continuous.webm',['-stream_loop','2','-i',str(media/'vp9.webm'),'-t','18','-c:v','copy','-an'])
 run('av1.webm',video('640x360')+['-threads','1','-c:v','libaom-av1','-usage','realtime','-cpu-used','8','-b:v','350k','-pix_fmt','yuv420p'])
 run('h264-10bit.mp4',video('640x360')+common+['-profile:v','high10','-pix_fmt','yuv420p10le'])
 run('h264-high-audio.mp4',['-f','lavfi','-i','testsrc2=size=1920x1080:rate=30','-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-t','12','-threads','1','-c:v','libx264','-preset','veryfast','-profile:v','high','-crf','26','-bf','3','-pix_fmt','yuv420p','-c:a','aac','-b:a','96k','-movflags','frag_keyframe+empty_moov+default_base_moof'])
 run('h264-high-long.mp4',['-stream_loop','5','-i',str(media/'h264-high-audio.mp4'),'-t','72','-c','copy'])
 metadata={'ffmpeg_version':subprocess.check_output([ffmpeg,'-version'],text=True).splitlines()[0],'generated_synthetic_media':True,'historical_original_bitstreams_not_recreated':True,'fixtures':records};(args.work.resolve()/'fixtures.json').write_text(json.dumps(metadata,indent=2)+'\n');print('Generated',len(records),'synthetic clips in',media)
if __name__=='__main__':main()
