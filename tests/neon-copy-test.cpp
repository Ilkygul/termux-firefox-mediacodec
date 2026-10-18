#include <arm_neon.h>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <vector>
#include <cstdio>
#include <chrono>
#include <sys/mman.h>
#include <unistd.h>
#define MOZ_ASSERT assert
#define MOZ_RELEASE_ASSERT assert
#define MOZ_WIDGET_GTK 1
namespace gfx { struct IntSize {int32_t width,height; bool operator!=(const IntSize&o)const{return width!=o.width||height!=o.height;}}; }
namespace old {
struct MappedYCbCrChannelData {uint8_t*data;gfx::IntSize size;int32_t stride,skip;uint32_t bytesPerPixel;bool CopyInto(MappedYCbCrChannelData&);};
static void CopyPlane(uint8_t* aDst, const uint8_t* aSrc,
                      const gfx::IntSize& aSize, int32_t aStride, int32_t aSkip,
                      int32_t aBytesPerElement) {
  int32_t height = aSize.height;
  int32_t width = aSize.width;
  const int32_t rowBytes = width * aBytesPerElement;

  // The interleaved (aSkip != 0) path steps over skipped elements between
  // pixels, so a row reaches further than the packed width. Computed with
  // 64-bit arithmetic.
  const int64_t srcRowSpan =
      (static_cast<int64_t>(width) + static_cast<int64_t>(width - 1) * aSkip) *
      aBytesPerElement;
  MOZ_RELEASE_ASSERT(srcRowSpan <= aStride);

  if (!aSkip) {
    // Fast path: planar input.
    memcpy(aDst, aSrc, height * aStride);
  } else {
    for (int y = 0; y < height; ++y) {
      const uint8_t* src = aSrc;
      uint8_t* dst = aDst;
      // Slow path
      for (int x = 0; x < width; ++x) {
        for (int b = 0; b < aBytesPerElement; ++b) {
          *dst++ = *src++;
        }
        src += aSkip * aBytesPerElement;
      }
      // Trailing stride bytes are not pixel data; zero them so
      // VideoFrame.copyTo() does not expose stale buffer contents to JS.
      memset(dst, 0, aStride - rowBytes);
      aSrc += aStride;
      aDst += aStride;
    }
  }
}
template <class PixelDataType>
static void copyData(PixelDataType* aDst,
                     const MappedYCbCrChannelData& aChannelDst,
                     PixelDataType* aSrc,
                     const MappedYCbCrChannelData& aChannelSrc) {
  uint8_t* srcByte = reinterpret_cast<uint8_t*>(aSrc);
  const int32_t srcSkip = aChannelSrc.skip + 1;
  uint8_t* dstByte = reinterpret_cast<uint8_t*>(aDst);
  const int32_t dstSkip = aChannelDst.skip + 1;
  for (int32_t i = 0; i < aChannelSrc.size.height; ++i) {
    for (int32_t j = 0; j < aChannelSrc.size.width; ++j) {
      *aDst = *aSrc;
      aSrc += srcSkip;
      aDst += dstSkip;
    }
    srcByte += aChannelSrc.stride;
    aSrc = reinterpret_cast<PixelDataType*>(srcByte);
    dstByte += aChannelDst.stride;
    aDst = reinterpret_cast<PixelDataType*>(dstByte);
  }
}
bool MappedYCbCrChannelData::CopyInto(MappedYCbCrChannelData& aDst) {
  if (!data || !aDst.data || size != aDst.size) {
    return false;
  }

  if (stride == aDst.stride && skip == aDst.skip) {
    // fast path!
    // We assume that the padding in the destination is there for alignment
    // purposes and doesn't contain useful data.
    memcpy(aDst.data, data, stride * size.height);
    return true;
  }

  if (aDst.skip == 0 && skip == 0) {
    // fast-ish path
    for (int32_t i = 0; i < size.height; ++i) {
      memcpy(aDst.data + i * aDst.stride, data + i * stride,
             size.width * bytesPerPixel);
    }
    return true;
  }

  MOZ_ASSERT(bytesPerPixel == 1 || bytesPerPixel == 2);
  // slow path
  if (bytesPerPixel == 1) {
    copyData(aDst.data, aDst, data, *this);
  } else if (bytesPerPixel == 2) {
    copyData(reinterpret_cast<uint16_t*>(aDst.data), aDst,
             reinterpret_cast<uint16_t*>(data), *this);
  }
  return true;
}
}
namespace opt {
struct MappedYCbCrChannelData {uint8_t*data;gfx::IntSize size;int32_t stride,skip;uint32_t bytesPerPixel;bool CopyInto(MappedYCbCrChannelData&);};
static void CopyPlane(uint8_t* aDst, const uint8_t* aSrc,
                      const gfx::IntSize& aSize, int32_t aStride, int32_t aSkip,
                      int32_t aBytesPerElement) {
  int32_t height = aSize.height;
  int32_t width = aSize.width;
  const int32_t rowBytes = width * aBytesPerElement;

  // The interleaved (aSkip != 0) path steps over skipped elements between
  // pixels, so a row reaches further than the packed width. Computed with
  // 64-bit arithmetic.
  const int64_t srcRowSpan =
      (static_cast<int64_t>(width) + static_cast<int64_t>(width - 1) * aSkip) *
      aBytesPerElement;
  MOZ_RELEASE_ASSERT(srcRowSpan <= aStride);

  if (!aSkip) {
    // Fast path: planar input.
    memcpy(aDst, aSrc, height * aStride);
#if defined(__aarch64__) && defined(__BIONIC__) && defined(MOZ_WIDGET_GTK)
  } else if (aSkip == 1 && aBytesPerElement == 1 && width > 0) {
    // NV12 chroma: extract every other byte with NEON. Leave a scalar tail
    // so a load never reads beyond the last valid sample of the V plane.
    for (int y = 0; y < height; ++y) {
      int x = 0;
      for (; x < width - 16; x += 16) {
        const uint8x16x2_t pixels = vld2q_u8(aSrc + 2 * x);
        vst1q_u8(aDst + x, pixels.val[0]);
      }
      for (; x < width; ++x) {
        aDst[x] = aSrc[2 * x];
      }
      // Preserve the existing guarantee that destination padding is zero.
      memset(aDst + width, 0, aStride - width);
      aSrc += aStride;
      aDst += aStride;
    }
#endif
  } else {
    for (int y = 0; y < height; ++y) {
      const uint8_t* src = aSrc;
      uint8_t* dst = aDst;
      // Slow path
      for (int x = 0; x < width; ++x) {
        for (int b = 0; b < aBytesPerElement; ++b) {
          *dst++ = *src++;
        }
        src += aSkip * aBytesPerElement;
      }
      // Trailing stride bytes are not pixel data; zero them so
      // VideoFrame.copyTo() does not expose stale buffer contents to JS.
      memset(dst, 0, aStride - rowBytes);
      aSrc += aStride;
      aDst += aStride;
    }
  }
}
template <class PixelDataType>
static void copyData(PixelDataType* aDst,
                     const MappedYCbCrChannelData& aChannelDst,
                     PixelDataType* aSrc,
                     const MappedYCbCrChannelData& aChannelSrc) {
  uint8_t* srcByte = reinterpret_cast<uint8_t*>(aSrc);
  const int32_t srcSkip = aChannelSrc.skip + 1;
  uint8_t* dstByte = reinterpret_cast<uint8_t*>(aDst);
  const int32_t dstSkip = aChannelDst.skip + 1;
  for (int32_t i = 0; i < aChannelSrc.size.height; ++i) {
    for (int32_t j = 0; j < aChannelSrc.size.width; ++j) {
      *aDst = *aSrc;
      aSrc += srcSkip;
      aDst += dstSkip;
    }
    srcByte += aChannelSrc.stride;
    aSrc = reinterpret_cast<PixelDataType*>(srcByte);
    dstByte += aChannelDst.stride;
    aDst = reinterpret_cast<PixelDataType*>(dstByte);
  }
}
bool MappedYCbCrChannelData::CopyInto(MappedYCbCrChannelData& aDst) {
  if (!data || !aDst.data || size != aDst.size) {
    return false;
  }

  if (stride == aDst.stride && skip == aDst.skip) {
    // fast path!
    // We assume that the padding in the destination is there for alignment
    // purposes and doesn't contain useful data.
    memcpy(aDst.data, data, stride * size.height);
    return true;
  }

  if (aDst.skip == 0 && skip == 0) {
    // fast-ish path
    for (int32_t i = 0; i < size.height; ++i) {
      memcpy(aDst.data + i * aDst.stride, data + i * stride,
             size.width * bytesPerPixel);
    }
    return true;
  }

#if defined(__aarch64__) && defined(__BIONIC__) && defined(MOZ_WIDGET_GTK)
  if (bytesPerPixel == 1 && aDst.bytesPerPixel == 1 && skip == 1 &&
      aDst.skip == 0 && size.width > 0 && size.height > 0 &&
      int64_t(size.width) * 2 - 1 <= stride && aDst.stride >= size.width) {
    // Interleaved 8-bit chroma to planar storage. Keeping a scalar tail
    // avoids a one-byte overread when this is the V channel of NV12.
    const uint8_t* src = data;
    uint8_t* dst = aDst.data;
    for (int32_t y = 0; y < size.height; ++y) {
      int32_t x = 0;
      for (; x < size.width - 16; x += 16) {
        const uint8x16x2_t pixels = vld2q_u8(src + 2 * x);
        vst1q_u8(dst + x, pixels.val[0]);
      }
      for (; x < size.width; ++x) {
        dst[x] = src[2 * x];
      }
      src += stride;
      dst += aDst.stride;
    }
    return true;
  }
#endif

  MOZ_ASSERT(bytesPerPixel == 1 || bytesPerPixel == 2);
  // slow path
  if (bytesPerPixel == 1) {
    copyData(aDst.data, aDst, data, *this);
  } else if (bytesPerPixel == 2) {
    copyData(reinterpret_cast<uint16_t*>(aDst.data), aDst,
             reinterpret_cast<uint16_t*>(data), *this);
  }
  return true;
}
}

int main(){
 size_t cases=0; const size_t page=sysconf(_SC_PAGESIZE);
 for(int w:{1,2,7,8,15,16,17,31,32,33,63,64,65,1919,1920,1921})
 for(int h:{1,3})for(int skip:{0,1,2})for(int b:{1,2})for(int pad:{0,4,32}){
  int span=(w+(w-1)*skip)*b, stride=span+pad;
  size_t need=skip?(h-1)*stride+span:h*stride;
  size_t pages=(need+page-1)/page;
  auto mem=(uint8_t*)mmap(nullptr,(pages+1)*page,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
  assert(mem!=MAP_FAILED); assert(!mprotect(mem+pages*page,page,PROT_NONE));
  uint8_t*src=mem+pages*page-need;
  for(size_t i=0;i<need;i++)src[i]=(i*37+91)%256;
  std::vector<uint8_t>a(h*stride+64,0xa5),c=a;
  old::CopyPlane(a.data()+32,src,{w,h},stride,skip,b);
  opt::CopyPlane(c.data()+32,src,{w,h},stride,skip,b);assert(a==c);
  int ds=w*b+pad; a.assign(h*ds+64,0xa5);c=a;
  old::MappedYCbCrChannelData s{src,{w,h},stride,skip,(uint32_t)b},d{a.data()+32,{w,h},ds,0,(uint32_t)b};
  opt::MappedYCbCrChannelData ss{src,{w,h},stride,skip,(uint32_t)b},dd{c.data()+32,{w,h},ds,0,(uint32_t)b};
  assert(s.CopyInto(d)==ss.CopyInto(dd));assert(a==c);
  munmap(mem,(pages+1)*page);cases++;
 }
 printf("guard_page_pixel_cases=%zu\n",cases);
 std::vector<uint8_t>src(3840*1080,0x93),dst(src.size());
 for(int kind=0;kind<2;kind++)for(int mode=0;mode<2;mode++){
  auto start=std::chrono::steady_clock::now();
  for(int i=0;i<400;i++){
   asm volatile("" ::: "memory");
   if(kind==0){if(mode==0)old::CopyPlane(dst.data(),src.data(),{1920,1080},3840,1,1);else opt::CopyPlane(dst.data(),src.data(),{1920,1080},3840,1,1);}
   else if(mode==0){old::MappedYCbCrChannelData s{src.data(),{1920,1080},3840,1,1},d{dst.data(),{1920,1080},1920,0,1};s.CopyInto(d);}
   else {opt::MappedYCbCrChannelData s{src.data(),{1920,1080},3840,1,1},d{dst.data(),{1920,1080},1920,0,1};s.CopyInto(d);}
  }
  double ms=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-start).count();
  printf("kind=%d optimized=%d iterations=400 ms=%.3f checksum=%d\n",kind,mode,ms,dst[1900]);
 }
}
