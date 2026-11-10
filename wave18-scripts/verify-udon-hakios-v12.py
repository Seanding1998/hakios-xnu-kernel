#!/usr/bin/env python3
"""Wave 18 verification of udon-hakios-grafted-v12.img (UFS S3-S8 build).

Shape identical to wave16-scripts/verify-udon-hakios-v11.py, with:
  - v12 is a CMDLINE-ONLY build: CONFIG_UFS_WRITE / CONFIG_VAR_STORE are
    runtime boot-args (docs/boot-args.md:309/:432), and `make kernel` after
    the two config lines produced a byte-identical binary (a7f4641f...), so
    the kernel entry is pinned byte-EQUAL to the v11 entry (the S3 write path,
    the ufs_check hasher and the var-save hook were already compiled in under
    CONFIG_HAKIOS_UFS=y; strings-check-v12.sh shows the v5-era loader already
    carries the darwin write offer);
  - the cmdline = the v11 bytes + " ufs_write=1 var_hfs=ufs_darwin_data
    ufs_check=1" (the only new tokens; ufs_native stays off -- N-step
    territory);
  - loader.efi / ramdisk / kernel.ver still byte-equal to the v11 entries
    (66c6b342 / 4f72da61 / afd473f5, the untouched v5/v6-era builds);
  - the FD still the untouched v4+ build (8924cb67), shim untouched (108ce972).

usage: verify-udon-hakios-v12.py IMG STOCK SHIM FD PAYLOAD_V12 PAYLOAD_V11 KERNEL_V11 CMDLINE_V12
"""
import struct, sys, gzip, hashlib

IMG, STOCK, SHIM, FD, PAYLOAD, PAYLOAD_V11, KERNEL_V11, CMDLINE_V12 = sys.argv[1:9]

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
kernel_v11 = open(KERNEL_V11, "rb").read()
cmdline_v12 = open(CMDLINE_V12, "rb").read()

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
check("FD is the untouched v4+ build (8924cb67)", sha(fd).startswith("8924cb67"), sha(fd)[:16])
check("shim is the untouched build (108ce972)", sha(shim).startswith("108ce972"), sha(shim)[:16])

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
check("cmdline ends with the new ufs_check=1 token", cmd.endswith("ufs_check=1"))
check("cmdline = v12 file bytes exactly", g[cmd_off:cmd_off + cmd_sz] == cmdline_v12)
check("cmdline has serial=0 + loader_return_after=60 (and not 300/20)",
      "serial=0" in cmd and "loader_return_after=60" in cmd
      and "loader_return_after=300" not in cmd and "loader_return_after=20" not in cmd)
check("cmdline has small_cores_after=0 (8 cores at once)", "small_cores_after=0" in cmd)
check("cmdline has touchscreen=1 (S3910 driver on)", "touchscreen=1" in cmd)
check("cmdline has buttons=1 buttons_map=1 (taro key order)",
      "buttons=1" in cmd and "buttons_map=1" in cmd)
check("cmdline has ufs=2 (loader block service)", cmd.count("ufs=2") == 1)
check("cmdline has ufs_write=1 exactly once (S3 write path on)", cmd.count("ufs_write=1") == 1)
check("cmdline has var_hfs=ufs_darwin_data (S6 arg; inert until a real init runs)",
      cmd.count("var_hfs=ufs_darwin_data") == 1)
check("cmdline has ufs_check=1 exactly once (R1 FNV comparison)", cmd.count("ufs_check=1") == 1)
check("cmdline has NO ufs_native (N-step stays off)",
      "ufs_native" not in cmd)
check("cmdline carries every v6 argument (soc_* set)",
      all(a in cmd for a in ("cpus=8", "bootcpu=7", "soc_ipa_base=0x3e40000", "soc_gsi_base=0x3e04000",
                             "soc_ipcc=0xed18000", "soc_rsc=0x17a20000", "soc_mpss_mem=0x8bc00000",
                             "modem_ipa_fw_at=0x8b910000", "soc_ipa_stream=0x5c0", "soc_ipa_stream_uc=0x5c2",
                             "soc_ipa_fw=ipa_fws")))
check("cmdline budget: len+68 reserve < 608", len(cmd) + 68 < 608, f"{len(cmd)}+68={len(cmd)+68}")

# wave 18: entry-level cmp against the v11 payload (cmdline-only delta)
def payload_entries(data):
    magic, size = struct.unpack_from("<II", data, 0)
    assert magic == 0x50554E58
    return {name: data[o:o + s] for name, (o, s) in walk_entries(data, 0, size).items()}

e12 = payload_entries(payload)
e11 = payload_entries(payload_v11)
check("kernel entry == the v11 build (byte-equal: config lines are runtime args)",
      e12["kernel"] == kernel_v11 == e11["kernel"], f"sha256 {sha(kernel_v11)[:16]}")
check("v12 kernel carries the S3/S4/S5 log strings",
      all(s in e12["kernel"] for s in (b"takes writes", b"everything else of the storage is read only",
                                       b"for the data volume", b"ufs: check ", b"the saver did not answer")))
check("cmdline entry = v11 entry + the three wave-18 tokens",
      e12["cmdline"] == e11["cmdline"][:-1] + b" ufs_write=1 var_hfs=ufs_darwin_data ufs_check=1\0")
check("cmdline byte-identical to the v12 cmdline file", e12["cmdline"] == cmdline_v12)
for name in ("loader.efi", "ramdisk", "kernel.ver"):
    check(f"{name} byte-equal to the v11 entry", e12[name] == e11[name], f"sha256 {sha(e12[name])[:16]}")
check("loader.efi is the v5/v6-era untouched build (66c6b342)", sha(e12["loader.efi"]).startswith("66c6b342"))
check("v5-era loader carries the darwin write offer (may be written this run)",
      b"may be written this run" in e12["loader.efi"])
check("ramdisk is the v6 resident-stub build (4f72da61)", sha(e12["ramdisk"]).startswith("4f72da61"))
check("kernel.ver is the v6 build (afd473f5)", sha(e12["kernel.ver"]).startswith("afd473f5"))

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
