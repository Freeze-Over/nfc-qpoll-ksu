#!/usr/bin/env python3
"""Minimal EROFS reader: walk directories and extract uncompressed files.

Only handles the common uncompressed layout; compressed inodes are reported.
"""
import struct
import sys

EROFS_SUPER_OFFSET = 1024
EROFS_MAGIC = 0xE0F5E1E2

# inode i_format layout bits
INODE_LAYOUT_MASK = 0x0007
INODE_FLAT_PLAIN = 0
INODE_COMPRESSED_FULL = 1
INODE_FLAT_INLINE = 2
INODE_COMPRESSED_COMPACT = 3
INODE_CHUNK_BASED = 4


class Erofs:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.f.seek(EROFS_SUPER_OFFSET)
        sb = self.f.read(128)
        magic, = struct.unpack_from("<I", sb, 0)
        if magic != EROFS_MAGIC:
            raise ValueError(f"bad magic {magic:#x}")
        self.blkszbits = sb[12]
        self.blksz = 1 << self.blkszbits
        self.root_nid, = struct.unpack_from("<H", sb, 14)
        self.blocks, = struct.unpack_from("<I", sb, 36)
        self.meta_blkaddr, = struct.unpack_from("<I", sb, 40)
        self.xattr_blkaddr, = struct.unpack_from("<I", sb, 44)
        self.feature_incompat, = struct.unpack_from("<I", sb, 80)
        print(f"erofs: blksz={self.blksz} root_nid={self.root_nid} blocks={self.blocks} meta={self.meta_blkaddr}")

    def inode_pos(self, nid):
        return self.meta_blkaddr * self.blksz + nid * 32

    def inode(self, nid):
        self.f.seek(self.inode_pos(nid))
        raw = self.f.read(32)
        i_format, i_xattr_icount, i_mode, i_nlink, i_size, i_reserved, raw_blkaddr, i_ino = struct.unpack(
            "<HHHHIIII", raw[:24]
        )
        return {
            "nid": nid,
            "format": i_format,
            "layout": i_format & INODE_LAYOUT_MASK,
            "mode": i_mode,
            "size": i_size,
            "raw_blkaddr": raw_blkaddr,
            "ino": i_ino,
            "is_dir": (i_mode & 0o170000) == 0o040000,
        }

    def read_data(self, ino, max_bytes=None):
        size = ino["size"]
        if max_bytes is not None:
            size = min(size, max_bytes)
        layout = ino["layout"]
        if layout == INODE_FLAT_PLAIN:
            self.f.seek(ino["raw_blkaddr"] * self.blksz)
            return self.f.read(size)
        if layout == INODE_FLAT_INLINE:
            self.f.seek(self.inode_pos(ino["nid"]) + 32)
            return self.f.read(size)
        return None

    def listdir(self, ino):
        data = self.read_data(ino)
        if data is None:
            return None
        out = []
        pos = 0
        while pos + 12 <= len(data):
            nid, nameoff, ftype = struct.unpack_from("<QHB", data, pos)
            if nameoff == 0 or pos + nameoff >= len(data):
                break
            end = data.find(b"\x00", pos + nameoff)
            if end < 0:
                end = len(data)
            name = data[pos + nameoff:end].decode("utf-8", "replace")
            if name:
                out.append((name, nid, ftype))
            pos += nameoff
            if nameoff == 0:
                break
        return out

    def walk(self, nid, path=""):
        ino = self.inode(nid)
        if not ino["is_dir"]:
            yield path, ino
            return
        entries = self.listdir(ino)
        if entries is None:
            print(f"  (compressed dir?) {path}")
            return
        for name, child, _ft in entries:
            if name in (".", ".."):
                continue
            yield from self.walk(child, f"{path}/{name}")


def main():
    img = sys.argv[1]
    targets = sys.argv[2:] or ["nfc_nci.st21nfc.st.so"]
    fs = Erofs(img)
    for path, ino in fs.walk(fs.root_nid):
        for t in targets:
            if path.endswith("/" + t) or path == "/" + t:
                print(f"FOUND {path} nid={ino['nid']} layout={ino['layout']} size={ino['size']} raw_blk={ino['raw_blkaddr']}")
                if ino["layout"] == INODE_FLAT_PLAIN:
                    data = fs.read_data(ino)
                    out = t
                    open(out, "wb").write(data)
                    print(f"  extracted -> {out} ({len(data)} bytes)")
                else:
                    print("  compressed/other layout; needs decompression")


if __name__ == "__main__":
    raise SystemExit(main())
