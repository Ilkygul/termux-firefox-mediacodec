#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import subprocess,json,hashlib,argparse,tempfile,shutil
parser=argparse.ArgumentParser(description='Check actual Firefox buffer ownership and bounds before a full build; not playback certification.')
parser.add_argument('--source',type=Path,required=True);parser.add_argument('--compiler',default='g++')
args=parser.parse_args();S=args.source.resolve()
temporary=tempfile.TemporaryDirectory(prefix='firefox-plane-check-');D=Path(temporary.name);inc=D/'includes';inc.mkdir();(inc/'mozilla').symlink_to(S/'mfbt',target_is_directory=True)
header=S/'dom/media/platforms/ffmpeg/FFmpegVideoUtils.h';text=header.read_text();functions=text[text.index('// A plane occupies'):text.index('\n#endif',text.index('// A plane occupies'))]
media=S/'dom/media/MediaData.h';text=media.read_text();types=text[text.index('  struct YCbCrBuffer {'):text.index('  // Constructs a VideoData object.')]
cpp=S/'dom/media/platforms/ffmpeg/FFmpegVideoDecoder.cpp';text=cpp.read_text();start=text.index('  VideoData::YCbCrBuffer boundsBuffer = b;');normalize=text[start:text.index('  if (!FramePlanesFitBackingBuffers',start)]
program=r'''#include <cstdint>
#include <cstddef>
#include <cassert>
#include <memory>
#include <type_traits>
#include "mozilla/CheckedInt.h"
extern "C" {
struct AVBufferRef { uint8_t* data; size_t size; };
struct AVFrame { AVBufferRef* buf[8]; };
}
using mozilla::CheckedInt;
template<class T> using UniquePtr=std::unique_ptr<T>;
template<class T> using RefPtr=std::shared_ptr<T>;
namespace layers { struct BufferRecycleBin {}; }
using MediaResult=int;
enum class E {Identity,UNKNOWN,COLOR_8,LIMITED,FULL};
struct VideoData {
using YUVColorSpace=E;using ColorSpace2=E;using ColorDepth=E;using ColorRange=E;using ChromaSubsampling=E;
'''+types+r'''
};
VideoData::QuantizableBuffer::~QuantizableBuffer()=default;
static_assert(!std::is_copy_constructible_v<VideoData::QuantizableBuffer>);
static_assert(std::is_copy_constructible_v<VideoData::YCbCrBuffer>);
'''+functions+r'''
int main() {
 uint8_t storage[48]{}; AVBufferRef ref{};ref.data=storage;ref.size=48;
 AVFrame frame{};frame.buf[0]=&ref;
 VideoData::QuantizableBuffer b;
 b.mPlanes[0]={storage,8,4,8,0};
 b.mPlanes[1]={storage+32,4,2,8,1};
 b.mPlanes[2]={storage+33,4,2,8,1};
 assert(!FramePlanesFitBackingBuffers(&frame,b));
 const bool isNV12=true;
'''+normalize+r'''
 assert(FramePlanesFitBackingBuffers(&frame,boundsBuffer));
 ref.size=47;assert(!FramePlanesFitBackingBuffers(&frame,boundsBuffer));ref.size=48;
 frame.buf[0]=nullptr;assert(!FramePlanesFitBackingBuffers(&frame,boundsBuffer));frame.buf[0]=&ref;
 boundsBuffer.mPlanes[0].mStride=UINT32_MAX;assert(!FramePlanesFitBackingBuffers(&frame,boundsBuffer));boundsBuffer.mPlanes[0].mStride=8;
 boundsBuffer.mPlanes[0].mHeight=UINT32_MAX;assert(!FramePlanesFitBackingBuffers(&frame,boundsBuffer));
}
'''
(D/'real-layout-test.cpp').write_text(program)
subprocess.run([args.compiler,'-std=c++20','-O2','-I'+str(inc),str(D/'real-layout-test.cpp'),'-o',str(D/'real-layout-test')],check=True)
subprocess.run([str(D/'real-layout-test')],check=True)
result={'actual_upstream_buffer_type_declarations':True,'owning_subclass_is_not_copyable':True,'plane_metadata_base_is_copyable':True,'candidate_bounds_normalization_compiles':True,'upstream_bounds_check_retained':True,'truncated_and_missing_buffers_rejected':True,'excessive_stride_and_height_rejected':True,'MediaData_h_sha256':hashlib.sha256(media.read_bytes()).hexdigest(),'not_browser_playback_certification':True}
print(json.dumps(result,sort_keys=True));temporary.cleanup()
