# Architecture and validated limits

The decoding path is:

```text
Firefox GTK/X11 (native Android/Bionic)
  -> system FFmpeg decoder module
     -> h264_mediacodec / vp9_mediacodec, ndk_codec=1
        -> Android MediaCodec / Qualcomm Codec2
  -> NV12 image planes
     -> existing Firefox planar-image or texture copy
        -> ARM64 NEON chroma extraction where applicable
  -> existing Firefox compositor / Termux:X11
```

Hardware video decoding and GPU compositing are separate functions. This implementation does not provide zero-copy Android surfaces, direct display scanout, general VA-API support, AV1 hardware decoding, or a new compositor. Decoded buffers still pass through Firefox's image pipeline.

## Ordered feature patches

1. `1001-system-ffmpeg-preference.patch`: `media.ffmpeg.preferred` opts into system FFmpeg priority, including before bundled FFVPX where needed.
2. `1002-native-mediacodec-prototype.patch`: `media.ffmpeg.mediacodec.enabled` enables the Bionic/GTK path for eligible system-FFmpeg decoders. Binder initialization uses `PR_CallOnce`; the pool is created only when an eligible decoder is requested. No separate service is started.
3. `1003-native-decoder-output-diagnostics.patch`: logs decoder description and actual hardware state on the existing first-output/state-change branch, only when explicitly requested through `MOZ_LOG`. Initialization-only descriptions can be provisional because decoder creation is lazy.
4. `1004-neon-interleaved-chroma.patch`: speeds up 8-bit skip-one copies in both image-container and mapped-texture paths. A scalar tail prevents the last V-plane load from crossing its valid range. Image-container padding remains zeroed; mapped texture padding remains unchanged.

The first two preferences default to false. An explicit `media.hardware-video-decoding.enabled=false` prevents hardware selection even if both feature preferences are enabled.

## Eligibility and fallback

Validated hardware streams are 8-bit H.264 with AVC configuration and supported profiles, and 8-bit VP9. Low-latency requests, alpha, higher bit depth and unsupported codecs do not use this path. Hardware initialization failure resets the MediaCodec state and tries the existing software decoder path.

The tested system runtime is FFmpeg 8.1.3, with `libavcodec.so.62` and `libavutil.so.60`. The source uses Firefox's versioned FFmpeg wrapper rather than a private replacement library. A future FFmpeg major ABI or decoder behavior change needs review and on-device retesting.

## Why the discarded proxy was not deployed

An earlier private FFmpeg proxy proved H.264 hardware decoding but could not make stock Firefox choose system FFmpeg for VP9, because bundled FFVPX had priority. The obsolete `media.ffvpx.enabled` preference did not solve that. Source integration resolved decoder selection directly. No proxy binary, `LD_LIBRARY_PATH` injection or permanent helper daemon is required in normal use.

## Native build compatibility changes

Five additional host patches address Rust native-host naming, Python's Android platform reporting, a private Android logging header in vendored glslopt, configurable ThinLTO for the on-device Rust link, and the API-24 `pthread_getname_np` header/runtime mismatch. They are separate from the four runtime feature patches and are not needed by the ordinary official Linux cross-build route.

Full Rust LTO exhausted memory during native development. ThinLTO completed successfully, with two compiler jobs on two CPU cores. Changing this build policy did not add a runtime memory service or globally replace the compiler.
