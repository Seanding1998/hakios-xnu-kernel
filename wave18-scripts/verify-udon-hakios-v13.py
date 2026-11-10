#!/usr/bin/env python3
"""Wave 18 verification of udon-hakios-grafted-v13.img (S6-S8, real-init chain).

Shape identical to wave18-scripts/verify-udon-hakios-v12.py, with:
  - a SIX-entry payload: the two new ramdisk entries
      resident = flashboot.apfs (the boot volume: stage0 as /sbin/launchd, md0,
                 the root the kernel starts from)
      ramdisk  = root.apfs     (init + rc + var.skel channel, md1 on /redwood)
    built by xnuloader/mkpayload.py from the byte-pinned loader.efi (66c6b342)
    and kernel.ver (afd473f5) entries and the fresh kernel (a7f4641f, byte-equal
    to the v11 hand-off: ROOT_APFS/VAR_HFS are runtime boot-args, like
    UFS_WRITE before them);
  - the cmdline = the v12 bytes + " root_apfs=ufs_darwin" (449 B, budget 516);
  - FD (8924cb67) and shim (108ce972) untouched.

usage: verify-udon-hakios-v13.py IMG STOCK SHIM FD PAYLOAD_V13 PAYLOAD_V11 CMDLINE_V13 FLASHBOOT_APFS ROOT_APFS
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD, PAYLOAD_V11, CMDLINE_V13, FLASHBOOT, ROOTAPFS = sys.argv[1:10]

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
payload_v11 = open(PAYLOAD_V11, "rb").read()
cmdline_v13 = open(CMDLINE_V13, "rb").read()
flashboot = open(FLASHBOOT, "rb").read()
rootapfs = open(ROOTAPFS, "rb").read()

print("[header]")
check("ANDROID! magic", img[:8] == b"ANDROID!")
hdr = bytearray(stock[:4096])
diff = [i for i in range(4096) if img[i] != stock[i]]
check("header diff vs stock is kernel_size/ramdisk_size only",
      all(8 <= i < 16 for i in diff), f"diff bytes {diff}")
ksz = struct.unpack_from("<I", img, 8)[0]
print(f"  kernel_size={ksz}")

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
check("FD is the untouched v4+ build (8924cb67)", sha(fd).startswith("8924cb67"), sha(fd)[:16])
check("shim is the untouched build (108ce972)", sha(shim).startswith("108ce972"), sha(shim)[:16])

print("[XNUP payload]")
poff = len(shim) + len(fd)
magic, size = struct.unpack_from("<II", g, poff)
check("magic XNUP", magic == 0x50554E58, f"{magic:08x}")
check("Size == len-8", size == len(payload) - 8, f"{size}")
check("container byte-equal to source", g[poff:poff + len(payload)] == payload)
check("payload fits the 64 MB window", len(payload) <= 0x4000000 - 0x1000, f"{len(payload)} B")

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
check("entries", set(entries) == {"loader.efi", "kernel", "resident", "ramdisk", "cmdline", "kernel.ver"},
      str({k: v[1] for k, v in entries.items()}))

cmd_off, cmd_sz = entries["cmdline"]
cmd = g[cmd_off:cmd_off + cmd_sz].decode().rstrip("\0")
print(f"  cmdline: {cmd}")
print("[cmdline]")
check("cmdline ends with root_apfs=ufs_darwin", cmd.endswith("root_apfs=ufs_darwin"))
check("cmdline = v13 file bytes exactly", g[cmd_off:cmd_off + cmd_sz] == cmdline_v13)
check("cmdline budget len+68 < 608", len(cmd) + 68 < 608, f"{len(cmd)}+68={len(cmd)+68}")
check("ufs=2 + ufs_write=1 (S3 write path)", cmd.count("ufs=2") == 1 and cmd.count("ufs_write=1") == 1)
check("var_hfs=ufs_darwin_data (S6 data volume)", cmd.count("var_hfs=ufs_darwin_data") == 1)
check("ufs_check=1 (R1 FNV comparison)", cmd.count("ufs_check=1") == 1)
check("root_apfs=ufs_darwin once (real-init chain)", cmd.count("root_apfs=ufs_darwin") == 1)
check("loader_return_after=60 and no ufs_native",
      "loader_return_after=60" in cmd and "ufs_native" not in cmd)
check("v6 soc_* set intact",
      all(a in cmd for a in ("cpus=8", "bootcpu=7", "soc_rsc=0x17a20000", "soc_ipa_fw=ipa_fws")))

def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e13 = payload_entries(payload)
e11 = payload_entries(payload_v11)
print("[entries]")
check("kernel == the v11 build (byte-equal)", e13["kernel"] == e11["kernel"], f"sha256 {sha(e13['kernel'])[:16]}")
check("kernel carries the S3/S4/S5 strings",
      all(s in e13["kernel"] for s in (b"takes writes", b"for the data volume", b"ufs: check ")))
check("loader.efi byte-equal to the v11 entry", e13["loader.efi"] == e11["loader.efi"], sha(e13["loader.efi"])[:16])
check("kernel.ver byte-equal to the v11 entry", e13["kernel.ver"] == e11["kernel.ver"], sha(e13["kernel.ver"])[:16])
check("resident entry == flashboot.apfs (build product)", e13["resident"] == flashboot, f"{len(flashboot)} B")
check("ramdisk entry == root.apfs (build product)", e13["ramdisk"] == rootapfs, f"{len(rootapfs)} B")
check("v5-era loader carries the resident/dual-ramdisk support",
      b"RAMDisk1" in e13["loader.efi"] and b"may be written this run" in e13["loader.efi"])
check("flashboot is an APFS container (NXSB @+32, the boot volume alone)", flashboot[32:36] == b"NXSB")
check("root.apfs is an APFS container (NXSB @+32)", rootapfs[32:36] == b"NXSB")
check("flashboot and root.apfs differ (two distinct containers)", flashboot != rootapfs)

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
