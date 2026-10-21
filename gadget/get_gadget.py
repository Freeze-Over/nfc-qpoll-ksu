#!/usr/bin/env python3
"""Download frida-gadget for android-arm64 and decompress it to gadget/libgadget.so.

Gadget is not committed to the repository (LGPL, large binary); it is fetched at
build time from the official Frida release, optionally through a mirror.
"""
import lzma
import os
import sys
import time
import urllib.request

VERSION = "17.24.3"
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "libgadget.so")

TARGET = (
    f"https://github.com/frida/frida/releases/download/{VERSION}/"
    f"frida-gadget-{VERSION}-android-arm64.so.xz"
)

MIRRORS = [
    TARGET,
    "https://ghproxy.net/" + TARGET,
    "https://ghfast.top/" + TARGET,
    "https://gh-proxy.com/" + TARGET,
]


def main() -> int:
    if os.path.exists(OUT) and os.path.getsize(OUT) > 1_000_000:
        print(f"already present: {OUT} ({os.path.getsize(OUT)} bytes)")
        return 0

    for url in MIRRORS:
        for attempt in range(3):
            try:
                print(f"fetching {url} (attempt {attempt + 1})")
                req = urllib.request.Request(url, headers={"User-Agent": "nfc-qpoll-ksu"})
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = resp.read()
                raw = lzma.decompress(data)
                with open(OUT, "wb") as fh:
                    fh.write(raw)
                print(f"ok: {OUT} ({len(raw)} bytes)")
                return 0
            except Exception as exc:  # noqa: BLE001 - report and try next mirror
                print(f"  failed: {type(exc).__name__}: {exc}")
                time.sleep(2)
    print("error: could not download frida-gadget; place it at", OUT, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
