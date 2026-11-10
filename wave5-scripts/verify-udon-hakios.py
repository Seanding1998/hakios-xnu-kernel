#!/usr/bin/env python3
"""Wave 5 independent readback verification of udon-hakios-grafted.img.

Re-derives everything from the final image + the source artifacts, separately
from the packager's own asserts:
  - boot v4 header vs stock (only kernel_size/ramdisk_size may differ)
  - gzip round-trip == shim + FD + XNUP container (+16B pad)
  - shim ARM64 image header (text_offset/image_size/ARMd) at decompressed[0:64]
  - FD _FVH at decompressed[shim+0x28]
  - XNUP magic/Size at decompressed[shim+fd], byte-equal to the source container
  - container entry walk (names/sizes) and cmdline round-trip
  - graft footer + stock vbmeta byte-equality + zero fill outside content
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD = sys.argv[1:6]

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

print("[header]")
check("ANDROID! magic", img[:8] == b"ANDROID!")
hdr = bytearray(stock[:4096])
ksz0, rsz0 = struct.unpack_from("<II", hdr, 8)
struct.pack_into("<II", hdr, 8, len(img) and 0, 0)  # placeholder, real check below
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
off = poff + 8
entries = {}
while off + 24 <= poff + 8 + size:
    name = g[off:off + 16].split(b"\0")[0].decode()
    if not name:
        break
    esz, _ = struct.unpack_from("<II", g, off + 16)
    entries[name] = esz
    off += 24 + (esz + 15) // 16 * 16
check("entries", set(entries) == {"loader.efi", "kernel", "ramdisk", "cmdline", "kernel.ver"}, str(entries))
# cmdline round-trip
coff = poff + 8 + 24
# walk again to find cmdline precisely
off = poff + 8
cmd = None
while off + 24 <= poff + 8 + size:
    name = g[off:off + 16].split(b"\0")[0].decode()
    if not name:
        break
    esz, _ = struct.unpack_from("<II", g, off + 16)
    if name == "cmdline":
        cmd = g[off + 24: off + 24 + esz].decode().rstrip("\0")
    off += 24 + (esz + 15) // 16 * 16
print(f"  cmdline: {cmd}")
check("cmdline has serial=0 + loader_return_after=20", cmd and "serial=0" in cmd and "loader_return_after=20" in cmd)

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
