#!/usr/bin/env python3
"""Wave 11 verification of udon-hakios-grafted-v6.img.

Shape identical to wave5-scripts/verify-udon-hakios.py (21 checks), with the
cmdline expectation changed to loader_return_after=60 and three extra
entry-level checks: the ramdisk entry equals the wave 11 resident stub and
the entries the wave did not touch (loader.efi, kernel, kernel.ver) are
byte-equal to the v5 payload.

usage: verify-udon-hakios-v6.py IMG STOCK SHIM FD PAYLOAD_V6 PAYLOAD_V5 RAMDISK_V6
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD, PAYLOAD_V5, RAMDISK_V6 = sys.argv[1:8]

def sha(b): return hashlib.sha256(b).hexdigest()
ok = 0

def check(name, cond, detail=""):
    global ok
    if not cond:
        sys.exit(f"FAIL: {name} {detail}")
    ok += 1
    print(f"  PASS {name} {detail}")

img = open(IMG, "rb").read()
stock = open(STOCK, "rb").read()
shim = open(SHIM, "rb").read()
fd = open(FD, "rb").read()
payload = open(PAYLOAD, "rb").read()
payload_v5 = open(PAYLOAD_V5, "rb").read()
ramdisk_v6 = open(RAMDISK_V6, "rb").read()

print("[header]")
check("ANDROID! magic", img[:8] == b"ANDROID!")
hdr = bytearray(stock[:4096])
ksz0, rsz0 = struct.unpack_from("<II", hdr, 8)
diff = [i for i in range(4096) if img[i] != stock[i]]
check("header diff vs stock is kernel_size/ramdisk_size only",
      all(8 <= i < 16 for i in diff), f"diff bytes {diff}")
ksz = struct.unpack_from("<I", img, 8)[0]
rsz = struct.unpack_from("<I", img, 12)[0]
print(f"  kernel_size={ksz} ramdisk_size={rsz} (stock {ksz0}/{rsz0})")

print("[payload pages]")
pages = (ksz + 4095) // 4096
content_end = 4096 + pages * 4096
kernel = img[4096:4096 + ksz]
check("kernel zero-padded to page", img[4096 + ksz:content_end] == b"\0" * (content_end - 4096 - ksz))

print("[gzip round-trip]")
g = gzip.decompress(kernel)
expected = shim + fd + payload
expected += b"\0" * (-len(expected) % 16)
check("gunzip == shim+fd+payload(+pad)", g == expected, f"{len(g)} B")
check("sha256 decompressed", sha(g))

print("[shim header]")
text_off, image_size = struct.unpack_from("<QQ", g, 8)
check("text_offset == 0xA7100000", text_off == 0xA7100000, hex(text_off))
check("image_size == shim+fd", image_size == len(shim) + len(fd), hex(image_size))
check("ARMd magic @0x38", g[0x38:0x3C] == b"ARMd")

print("[FD]")
check("_FVH at shim+0x28", g[len(shim) + 0x28: len(shim) + 0x2C] == b"_FVH")
check("FD bytes equal source", g[len(shim):len(shim) + len(fd)] == fd)

print("[XNUP payload]")
poff = len(shim) + len(fd)
magic, size = struct.unpack_from("<II", g, poff)
check("magic XNUP", magic == 0x50554E58, f"{magic:08x}")
check("Size == len-8", size == len(payload) - 8, f"{size}")
check("container byte-equal to source", g[poff:poff + len(payload)] == payload)

def walk_entries(buf, base, size):
    out = {}
    off = base + 8
    while off + 24 <= base + 8 + size:
        name = buf[off:off + 16].split(b"\0")[0].decode()
        if not name:
            break
        esz, _ = struct.unpack_from("<II", buf, off + 16)
        out[name] = (off + 24, esz)
        off += 24 + (esz + 15) // 16 * 16
    return out

entries = walk_entries(g, poff, size)
check("entries", set(entries) == {"loader.efi", "kernel", "ramdisk", "cmdline", "kernel.ver"}, str({k: v[1] for k, v in entries.items()}))

# cmdline round-trip
cmd_off, cmd_sz = entries["cmdline"]
cmd = g[cmd_off:cmd_off + cmd_sz].decode().rstrip("\0")
print(f"  cmdline: {cmd}")
check("cmdline has serial=0 + loader_return_after=60", cmd and "serial=0" in cmd and "loader_return_after=60" in cmd and "loader_return_after=20" not in cmd)

# wave 11: entry-level cmp against the v5 payload and the new ramdisk stub
def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e6 = payload_entries(payload)
e5 = payload_entries(payload_v5)
check("ramdisk entry == wave11 resident stub", e6["ramdisk"] == ramdisk_v6, f"stub sha256 {sha(ramdisk_v6)[:16]}")
check("ramdisk differs from v5 hello", e6["ramdisk"] != e5["ramdisk"])
for name in ("loader.efi", "kernel", "kernel.ver"):
    check(f"{name} byte-equal to v5 entry", e6[name] == e5[name], f"sha256 {sha(e6[name])[:16]}")
check("cmdline differs from v5 only in loader_return_after",
      e6["cmdline"].replace(b"loader_return_after=60", b"loader_return_after=20") == e5["cmdline"])

print("[graft]")
fm, fver, _, orig, voff, vsz = struct.unpack_from(">4sIIQQQ", img, len(img) - 64)
check("footer AVBf v1.0", fm == b"AVBf" and fver == 1)
check("orig_size == vbmeta_offset == content end", orig == voff == content_end, f"{voff}")
vb = img[voff:voff + vsz]
check("vbmeta size 2432", vsz == 2432)
stock_vb_off = struct.unpack_from(">Q", stock, len(stock) - 64 + 20)[0]
stock_vb_size = struct.unpack_from(">Q", stock, len(stock) - 64 + 28)[0]
check("vbmeta == stock bytes @stock footer offset",
      vb == stock[stock_vb_off:stock_vb_off + stock_vb_size])
check("zero fill between vbmeta end and footer",
      img[voff + vsz:len(img) - 64] == b"\0" * (len(img) - 64 - voff - vsz))
check("final size 192 MiB", len(img) == 201326592)

print(f"\nALL {ok} CHECKS PASSED")
print("final sha256:", sha(img))
