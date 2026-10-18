# SPDX-License-Identifier: MPL-2.0
from pathlib import Path
import os
B=Path(__file__).resolve().parent
P=Path('/data/data/com.termux/files/usr')
def build_env():
 env=os.environ.copy()
 for k in ['LD_PRELOAD','LD_LIBRARY_PATH','RUSTUP_HOME','RUSTC_WRAPPER','MOZ_CONFIGURE_OPTIONS','CC','CXX','CFLAGS','CXXFLAGS','CPPFLAGS','LDFLAGS']:env.pop(k,None)
 env.update(LD_PRELOAD=str(P/'lib/libtermux-exec-ld-preload.so'),PATH=str(B/'native-build-tools/bin')+':'+str(P/'bin')+':/system/bin',
  MACH_BUILD_PYTHON_NATIVE_PACKAGE_SOURCE='none',PYTHONNOUSERSITE='1',
  MOZBUILD_STATE_PATH=str(B/'mozbuild-state'),MOZCONFIG=str(B/'source-baseline/.mozconfig'),
  FOLD_NATIVE_RUST_LTO='thin',
  CARGO_HOME=str(B/'cargo-cache'),CARGO_BUILD_JOBS='1',CARGO_PROFILE_RELEASE_DEBUG='0',
  RUSTFLAGS='-C debuginfo=0',CARGO_TARGET_AARCH64_LINUX_ANDROID_RUSTFLAGS='-C debuginfo=0',
  CC=str(B/'native-build-tools/bin/fold-native-clang'),CXX=str(B/'native-build-tools/bin/fold-native-clang++'),HOST_CC=str(B/'native-build-tools/bin/fold-native-clang'),HOST_CXX=str(B/'native-build-tools/bin/fold-native-clang++'),
  AR=str(P/'bin/llvm-ar'),RANLIB=str(P/'bin/llvm-ranlib'),
  CFLAGS='-O2 -fPIC -D__TERMUX__=1',CXXFLAGS='-O2 -fPIC -D__TERMUX__=1 -U__ANDROID__ -D_LIBCPP_HAS_NO_C11_ALIGNED_ALLOC',
  CPPFLAGS='-I'+str(P/'include'),LDFLAGS='-L'+str(P/'lib')+' -Wl,-rpath,'+str(P/'lib')+' -landroid-shmem -landroid-spawn -llog',
  HOST_CFLAGS='-O2 -D__TERMUX__=1',HOST_CXXFLAGS='-O2 -D__TERMUX__=1 -U__ANDROID__ -D_LIBCPP_HAS_NO_C11_ALIGNED_ALLOC',
  PKG_CONFIG=str(P/'bin/pkg-config'),PKG_CONFIG_LIBDIR=str(P/'lib/pkgconfig')+':'+str(P/'share/pkgconfig'),
  CBINDGEN=str(B/'native-build-tools/bin/cbindgen'),LIBCLANG_PATH=str(P/'lib'),
  BINDGEN_CFLAGS='--target=aarch64-linux-android24 -I'+str(P/'include'),
  BINDGEN_EXTRA_CLANG_ARGS_AARCH64_LINUX_ANDROID='--target=aarch64-linux-android24 -I'+str(P/'include'))
 return env
