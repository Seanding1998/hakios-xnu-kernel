#!/usr/bin/env python3
"""Wave 21.1 verification of udon-hakios-grafted-v16.img (the delayed first try -> SSH verdict).

Shape identical to wave21-scripts/verify-udon-hakios-v15.py, with:
  - the loader CHANGES: usb_init_kick + the 5 s settle before the first start_ex + the 20 s
    retry tempo + failed tries print their start_ex status (d612958d);
  - the cmdline = v16 bytes: loader_return_after 180 (F6 vnode-cliff bypass), en0_addr kept;
  - the kernel is BYTE-IDENTICAL to v15 (17c905ec -- the en0 driver already lives there);
  - resident/ramdisk byte-pinned to the v15 payload's entries (the darwin front stays untouched);
  - FD (8924cb67) and shim (108ce972) untouched.

usage: verify-udon-hakios-v16.py IMG STOCK SHIM FD PAYLOAD_V16 PAYLOAD_V15 CMDLINE_V16 KERNEL_FILE
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD, PAYLOAD_V15, CMDLINE_V16, KFILE = sys.argv[1:9]

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
payload_v15 = open(PAYLOAD_V15, "rb").read()
cmdline_v16 = open(CMDLINE_V16, "rb").read()
kfile = open(KFILE, "rb").read()

print("[header]")
check("ANDROID! magic", img[:8] == b"ANDROID!")
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
check("entries (usb joins: the USB server is up before the kernel)",
      set(entries) == {"loader.efi", "kernel", "resident", "ramdisk", "cmdline", "kernel.ver", "usb"},
      str({k: v[1] for k, v in entries.items()}))
cmd_off, cmd_sz = entries["cmdline"]
cmd = g[cmd_off:cmd_off + cmd_sz].decode().rstrip("\0")
print(f"  cmdline: {cmd}")
print("[cmdline]")
check("cmdline = v16 file bytes exactly", g[cmd_off:cmd_off + cmd_sz] == cmdline_v16)
check("cmdline ends with en0_addr=10.0.0.2 (the en0 link turns on)",
      cmd.endswith("root_apfs=ufs_darwin hw_target=D22ap en0_addr=10.0.0.2"))
check("cmdline budget len+122 < 608", len(cmd) + 122 < 608, f"{len(cmd)}+122={len(cmd)+122}")
check("loader_return_after=180 (the F6 vnode cliff at ~218 s stays out of reach)",
      cmd.count("loader_return_after=180") == 1)
check("no loader_return_after=300/120 leftovers",
      cmd.count("loader_return_after=300") == 0 and cmd.count("loader_return_after=120") == 0)
check("ufs_check still gone (path proven in wave18)", cmd.count("ufs_check") == 0)
check("ufs=2 + ufs_write=1 + var_hfs=ufs_darwin_data kept (S3-S8)",
      cmd.count("ufs=2") == 1 and cmd.count("ufs_write=1") == 1 and cmd.count("var_hfs=ufs_darwin_data") == 1)
check("root_apfs=ufs_darwin once (real-init chain)", cmd.count("root_apfs=ufs_darwin") == 1)
check("v14 soc_* set intact",
      all(a in cmd for a in ("cpus=8", "bootcpu=7", "soc_rsc=0x17a20000", "soc_ipa_fw=ipa_fws")))

def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e16 = payload_entries(payload)
e15 = payload_entries(payload_v15)
print("[entries]")
check("kernel == the v15 build, byte for byte (en0 already in; kernel did not move)",
      e16["kernel"] == kfile == e15["kernel"], f"sha256 {sha(e16['kernel'])[:16]}")
check("kernel carries the en0 boot-arg name", b"en0_addr" in e16["kernel"])
check("kernel carries the net ring's own line", b"10.0.0.2/30" in e16["kernel"])
check("kernel keeps the S3/S4/S5 write strings",
      all(s in e16["kernel"] for s in (b"takes writes", b"for the data volume", b"ufs: check ")))
check("kernel keeps the s3910 TouchComm driver", b"TouchComm v" in e16["kernel"])
check("loader.efi is the v16 delayed-first-try build, not v15.3",
      sha(e16["loader.efi"]).startswith("d612958d") and e16["loader.efi"] != e15["loader.efi"],
      sha(e16["loader.efi"])[:16])
check("loader.efi carries the settle line and the status print",
      all(s in e16["loader.efi"] for s in (b"five quiet seconds", b"try failed: start_ex %x")))
check("loader.efi carries netmode/netstat and the ring's line",
      all(s in e16["loader.efi"] for s in (b"oem netmode", b"oem netstat", b"the ring is on the page")))
check("loader.efi keeps the d22ap identity (D22AP + iPhone10,3)",
      all(s in e16["loader.efi"] for s in (b"D22AP", b"iPhone10,3")))
check("kernel.ver byte-equal to the v15 entry (v11 hand-off)", e16["kernel.ver"] == e15["kernel.ver"],
      sha(e16["kernel.ver"])[:16])
check("kernel.ver is the afd473f5 stamp", sha(e16["kernel.ver"]).startswith("afd473f5"), sha(e16["kernel.ver"])[:16])
check("resident entry byte-equal to the v15 entry (darwin front untouched)",
      e16["resident"] == e15["resident"], f"{len(e16['resident'])} B")
check("ramdisk entry byte-equal to the v15 entry", e16["ramdisk"] == e15["ramdisk"], f"{len(e16['ramdisk'])} B")
check("usb entry says 1", e16["usb"] == b"1\0", repr(e16["usb"]))
check("loader carries the dual-ramdisk/resident support",
      b"RAMDisk1" in e16["loader.efi"] and b"may be written this run" in e16["loader.efi"])
check("resident is an APFS container (NXSB @+32)", e16["resident"][32:36] == b"NXSB")
check("ramdisk is an APFS container (NXSB @+32)", e16["ramdisk"][32:36] == b"NXSB")

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
