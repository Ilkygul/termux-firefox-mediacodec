#!/data/data/com.termux/files/usr/bin/sh
# Browser-private Binder compatibility; normal Firefox binary remains native.
export LD_LIBRARY_PATH="/data/data/com.termux/files/usr/lib/firefox/native-system${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec /data/data/com.termux/files/usr/lib/firefox/firefox "$@"
