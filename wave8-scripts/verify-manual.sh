#!/bin/bash
# Wave8: manual-equivalent verification of the usb-mode container + graft geometry (fixed)
set -e
cd HOST-REDACTED/.zcode/workspace/9bfbfb72-21e9-4ab6-97a0-ac91b6869dc7/hakios-phk110
python3 - <<'EOF'
import struct, hashlib, json, gzip

img = open("device-layer/udon-hakios-usbmode-grafted-v3.img", "rb").read()
stock = open("device-layer/stock-boot-a.img", "rb").read()
payload = open("device-layer/udon-hakios-payload-usbmode-v3.bin", "rb").read()
loader = open("device-layer/udon-hakios-loader-usbmode-v3.efi", "rb").read()
shim = open("device-layer/udon-hakios-BootShim.bin", "rb").read()
fd = open("/home/HOST-REDACTED/hakios/uefi-udon/Build/udonPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd", "rb").read()
rep = json.load(open("device-layer/udon-hakios-usbmode-grafted-v3.report.json"))
assert hashlib.sha256(img).hexdigest() == rep["final_sha256"]
print("PASS report sha == image sha")

page = 4096
assert img[0:8] == b"ANDROID!", "magic"
ksize = struct.unpack_from("<I", img, 8)[0]
rsize = struct.unpack_from("<I", img, 12)[0]
assert (ksize, rsize) == (1302741, 0), (ksize, rsize)
print("PASS kernel_size/ramdisk_size = 1302741/0")
kern = img[page:page+ksize]
assert hashlib.sha256(kern).hexdigest() == rep["kernel_gzip_sha256"]
print("PASS kernel gzip sha matches report")
dec = gzip.decompress(kern)
assert len(dec) == rep["combined_bytes"] == 4261280
print("PASS gunzip == 4261280 B")
assert dec[0:240] == shim, "shim bytes differ"
print("PASS shim 240 B byte-equal")
assert dec[240:240+4194304] == fd, "FD bytes differ"
print("PASS FD 4194304 B byte-equal Wave7 build product")
rest = dec[240+4194304:]
assert rest[0:len(payload)] == payload, "payload bytes differ"
print("PASS XNUP container byte-equal to source payload,", len(payload), "B (rest is zero pad,", len(rest)-len(payload), "B)")
assert rest[len(payload):] == b"\0" * (len(rest) - len(payload)), "pad not zero"
print("PASS pad zero")

# XNUP entries
assert struct.unpack_from("<I", payload, 0)[0] == 0x50554E58
size = struct.unpack_from("<I", payload, 4)[0]
assert size == len(payload) - 8
entries = {}
off = 8
while off < size:
    name_raw, vl, _res = struct.unpack_from("<16sII", payload, off)
    if name_raw.rstrip(b"\0") == b"":
        break  # mkpayload's 24 zero-byte terminator
    off += 24
    entries[name_raw.rstrip(b"\0").decode()] = payload[off:off+vl]
    off += vl + (-vl % 16)
print("entries:", {k: len(v) for k, v in entries.items()})
assert set(entries) == {"loader.efi", "usb", "kernel.ver"}
print("PASS entries == {loader.efi, usb, kernel.ver} (usb-mode form)")
assert entries["usb"].rstrip(b"\0") == b"1"
print("PASS usb entry == '1'")
assert entries["loader.efi"] == loader
print("PASS loader.efi entry byte-equal udon-hakios-loader-usbmode-v3.efi")
print("kernel.ver:", entries["kernel.ver"].rstrip(b"\0").decode())
assert "cmdline" not in entries
print("PASS cmdline entry absent (usb-mode defaults)")

# graft geometry: container=first 1310720 bytes, vbmeta at 1310720, zero fill, footer at end
cont = img[0:1310720]
assert hashlib.sha256(cont).hexdigest() == rep["container_sha256"]
print("PASS container (0..1310720) sha matches report == unsigned image")
voff = 1310720
vb = img[voff:voff+2432]
assert vb == stock[rep["stock_vbmeta_offset"]:rep["stock_vbmeta_offset"]+2432]
print("PASS vbmeta 2432 B byte-equal stock OEM vbmeta")
foot = img[-64:]
assert foot[0:4] == b"AVBf"
ver, ver_minor, orig, voff_f, vsz = struct.unpack_from(">IIQQQ", foot, 4)  # AVB is big-endian
assert ver == 1 and ver_minor == 0 and orig == 1310720 and voff_f == 1310720 and vsz == 2432
print("PASS footer AVBf v1.0; orig == voff == 1310720, vbmeta_size 2432")
assert img[voff+2432:len(img)-64] == b"\0" * (len(img) - 64 - (voff+2432)), "nonzero region between vbmeta and footer"
print("PASS zero fill vbmeta -> footer")
assert len(img) == 201326592
print("PASS final size 192 MiB")
print("ALL MANUAL CHECKS PASS")
EOF
