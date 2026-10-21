#!/usr/bin/env python3
"""Find the ELF file that contains a byte pattern inside a partition image.

Uses program headers (PT_LOAD) to compute the file size, so it also works for
libraries whose section headers are stripped.
"""
import struct
import sys


def elf_extent(data, off):
    """Return (start, end) of the ELF at off, or None."""
    if off + 64 > len(data):
        return None
    if data[off:off + 4] != b"\x7fELF" or data[off + 4] != 2:
        return None
    hdr = data[off:off + 64]
    e_phoff, = struct.unpack_from("<Q", hdr, 0x20)
    e_phentsize, = struct.unpack_from("<H", hdr, 0x36)
    e_phnum, = struct.unpack_from("<H", hdr, 0x38)
    e_shoff, = struct.unpack_from("<Q", hdr, 0x28)
    e_shentsize, = struct.unpack_from("<H", hdr, 0x3A)
    e_shnum, = struct.unpack_from("<H", hdr, 0x3C)
    if not (0 < e_phnum < 64 and e_phentsize == 56):
        return None
    if e_phoff + e_phnum * e_phentsize > len(data):
        return None
    end = 0
    for i in range(e_phnum):
        p_off = e_phoff + i * e_phentsize
        p_offset, = struct.unpack_from("<Q", data, off + p_off + 0x08)
        p_filesz, = struct.unpack_from("<Q", data, off + p_off + 0x20)
        end = max(end, p_offset + p_filesz)
    if 0 < e_shnum < 200 and e_shentsize:
        end = max(end, e_shoff + e_shentsize * e_shnum)
    if not (0 < end < (64 << 20)):
        return None
    return off, end


def main():
    img, needle_hex, out = sys.argv[1], sys.argv[2], sys.argv[3]
    needle = bytes.fromhex(needle_hex)
    with open(img, "rb") as fh:
        data = fh.read()
    hit = data.find(needle)
    if hit < 0:
        print("pattern not found")
        return 1
    print(f"pattern at {hit:#x}")

    candidates = []
    pos = 0
    while True:
        pos = data.find(b"\x7fELF", pos)
        if pos < 0 or pos > hit:
            break
        ext = elf_extent(data, pos)
        if ext and ext[0] <= hit < ext[1]:
            candidates.append(ext)
        pos += 1

    if not candidates:
        print("no containing ELF found")
        return 1
    start, end = candidates[-1]
    print(f"container ELF at {start:#x} size {end - start} end {end:#x}")
    with open(out, "wb") as fh:
        fh.write(data[start:end])
    print(f"wrote {out} ({end - start} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
