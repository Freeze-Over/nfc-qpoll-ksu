#!/usr/bin/env python3
"""Scan an ext4 partition image for byte patterns, and carve the containing ELF."""
import struct
import sys


def find_all(fh, pattern, chunk=8 << 20):
    fh.seek(0)
    overlap = len(pattern) - 1
    prev = b""
    offset = 0
    while True:
        data = fh.read(chunk)
        if not data:
            return
        buf = prev + data
        start = 0
        while True:
            i = buf.find(pattern, start)
            if i < 0:
                break
            yield offset - len(prev) + i
            start = i + 1
        offset += len(data)
        prev = buf[-overlap:] if overlap else b""


def context(fh, off, before=48, after=80):
    fh.seek(max(0, off - before))
    data = fh.read(before + len(b"")+ after)
    ascii_part = bytes(c if 32 <= c < 127 else 46 for c in data)
    return ascii_part.decode("ascii", "replace")


def carve_elf(fh, hit, back=6 << 20):
    start_scan = max(0, hit - back)
    fh.seek(start_scan)
    data = fh.read(hit - start_scan + 8)
    idx = data.rfind(b"\x7fELF")
    while idx >= 0:
        off = start_scan + idx
        fh.seek(off)
        hdr = fh.read(64)
        if len(hdr) == 64 and hdr[4] == 2:  # ELF64
            e_shoff, = struct.unpack_from("<Q", hdr, 0x28)
            e_shentsize, = struct.unpack_from("<H", hdr, 0x3A)
            e_shnum, = struct.unpack_from("<H", hdr, 0x3C)
            end = e_shoff + e_shentsize * e_shnum
            if 0 < e_shnum < 100 and end < (1 << 31):
                return off, end
        idx = data.rfind(b"\x7fELF", 0, idx)
    return None


def main():
    path, *patterns = sys.argv[1:]
    with open(path, "rb") as fh:
        for pat in patterns:
            needle = pat.encode()
            print(f"== {pat} ==")
            for hit in find_all(fh, needle):
                info = carve_elf(fh, hit)
                extra = f" elf@{info[0]} size~{info[1]}" if info else " (no ELF found)"
                print(f"  @{hit:#x}{extra}")
                print("    " + context(fh, hit).replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
