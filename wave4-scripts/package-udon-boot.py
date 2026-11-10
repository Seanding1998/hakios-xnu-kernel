#!/usr/bin/env python3
"""Package the udonPkg UEFI FD into a PHK110-flashable boot_b image (wave 4,
extended in wave 5 to append an optional "XNUP" payload container).

Container: stock-aligned Android boot image v4 (the proven UniXNU-udon shape):
  - header page copied byte-for-byte from stock-boot-a.img (page size 4096,
    header_size 1584, os_version/reserved/cmdline/boot-signature fields verbatim),
    only kernel_size and ramdisk_size are rewritten;
  - kernel payload = gzip(BootShim.bin + SILICIUM_UEFI.fd [+ XNUP container],
    zero-padded to 16 bytes) where the shim's ARM64 image header satisfies
    decompressed[8:24] == (0xA7100000, shim+fd size); the shim (built with
    PAYLOAD_BASE, wave 5) copies the XNUP container that directly follows the
    FD to 0xF4000000 before entering the FD;
  - no DTB: ABL applies its runtime memory fixups to the vendor_boot DTB;
  - AVB: stock OEM vbmeta blob moved immediately after the image content and a
    fresh 64-byte AVBf footer appended (graft-boot-footer.py semantics), so the
    whole image still fills the stock 192 MiB boot partition.
"""
import argparse, gzip, hashlib, json, struct, sys
from pathlib import Path

V4_PAGE = 4096
FOOTER = struct.Struct(">4sIIQQQ")
PAYLOAD_BASE = 0xF4000000
PAYLOAD_MAX = 0x04000000

def sha(b): return hashlib.sha256(b).hexdigest()

def stock_footer(img):
    assert len(img) >= 64
    magic, _, _, original, off, size = FOOTER.unpack_from(img, len(img) - 64)
    assert magic == b"AVBf", "stock image has no AVB footer"
    vb = img[off:off + size]
    assert vb[:4] == b"AVB0", "stock vbmeta blob invalid"
    return original, off, size, vb

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fd", required=True, type=Path)
    ap.add_argument("--shim", required=True, type=Path)
    ap.add_argument("--stock", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--payload", type=Path, help="XNUP container (mkpayload.py) appended after the FD; shim must be built with PAYLOAD_BASE")
    ap.add_argument("--unsigned-out", type=Path, help="also write the pre-graft container")
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()

    fd = a.fd.read_bytes()
    shim = a.shim.read_bytes()
    stock = a.stock.read_bytes()
    payload = a.payload.read_bytes() if a.payload else b""
    assert len(fd) == 0x400000, f"FD size {len(fd):#x} != 0x400000"
    assert fd[40:44] == b"_FVH", "FD lacks EFI FV header signature"
    # shim header convention (REQUIRES_KERNEL_HEADER=1)
    text_off, image_size = struct.unpack_from("<QQ", shim, 8)
    assert text_off == 0xA7100000, f"shim text_offset {text_off:#x}"
    assert image_size == len(shim) + len(fd), f"shim image_size {image_size:#x} != shim+fd"
    # XNUP container (wave 5): mkpayload.py header = magic + u32 size (bytes after header)
    if payload:
        pmagic, psize = struct.unpack_from("<II", payload, 0)
        assert pmagic == 0x50554E58, f"payload magic {pmagic:#x} != XNUP"
        assert psize == len(payload) - 8, f"payload Size {psize} != len-8"
        assert len(payload) <= PAYLOAD_MAX - 0x1000, f"payload {len(payload)} exceeds {PAYLOAD_MAX:#x}-4K"

    combined = shim + fd + payload
    combined += b"\0" * (-len(combined) % 16)
    kernel = gzip.compress(combined, 9, mtime=0)

    # stock v4 header page, verbatim except kernel_size/ramdisk_size
    hdr = bytearray(stock[:V4_PAGE])
    assert hdr[:8] == b"ANDROID!"
    ks0, rs0, osv, hsize = struct.unpack_from("<4I", hdr, 8)
    hver = struct.unpack_from("<I", hdr, 0x28)[0]
    assert hver == 4 and hsize == 1584, f"stock header v{hver} size {hsize}"
    struct.pack_into("<II", hdr, 8, len(kernel), 0)

    pages = (len(kernel) + V4_PAGE - 1) // V4_PAGE
    image = bytes(hdr) + kernel + b"\0" * (pages * V4_PAGE - len(kernel))

    # graft: stock vbmeta + refreshed footer over the stock partition size
    so, soff, ssize, vbmeta = stock_footer(stock)
    partition = len(stock)
    assert len(image) + len(vbmeta) + 64 <= partition, "graft does not fit stock partition"
    out = bytearray(partition)
    out[:len(image)] = image
    out[len(image):len(image) + len(vbmeta)] = vbmeta
    footer = FOOTER.pack(b"AVBf", 1, 0, len(image), len(image), len(vbmeta))
    out[-64:] = footer + b"\0" * (64 - len(footer))

    # readback verification
    rb = bytes(out)
    assert rb[:8] == b"ANDROID!"
    ksz, rsz = struct.unpack_from("<II", rb, 8)
    assert rb[V4_PAGE:V4_PAGE + ksz] == kernel, "kernel readback mismatch"
    g = gzip.decompress(rb[V4_PAGE:V4_PAGE + ksz])
    assert g == combined, "gzip round-trip mismatch"
    assert struct.unpack_from("<QQ", g, 8) == (0xA7100000, len(shim) + len(fd))
    if payload:
        off = len(shim) + len(fd)
        assert struct.unpack_from("<II", g, off) == (0x50554E58, len(payload) - 8), "payload magic/size at shim+fd offset"
        pad = len(combined) - (len(shim) + len(fd) + len(payload))
        assert pad < 16 and (pad == 0 or g[-pad:] == b"\0" * pad), "bad 16-byte tail padding"
    fm, fver, _, orig, voff, vsz = FOOTER.unpack_from(rb, len(rb) - 64)
    assert fm == b"AVBf" and voff == len(image) and vsz == len(vbmeta)
    assert rb[voff:voff + vsz] == vbmeta, "vbmeta readback mismatch"

    if a.unsigned_out:
        a.unsigned_out.write_bytes(image)
    a.out.write_bytes(rb)

    report = {
        "fd_bytes": len(fd), "fd_sha256": sha(fd),
        "shim_bytes": len(shim), "shim_sha256": sha(shim),
        "payload_bytes": len(payload), "payload_sha256": sha(payload) if payload else None,
        "payload_base": hex(PAYLOAD_BASE) if payload else None,
        "combined_bytes": len(combined), "combined_sha256": sha(combined),
        "kernel_gzip_bytes": len(kernel), "kernel_gzip_sha256": sha(kernel),
        "container_bytes": len(image), "container_sha256": sha(image),
        "stock_kernel_size": ks0, "stock_ramdisk_size": rs0,
        "stock_vbmeta_offset": soff, "stock_vbmeta_size": ssize, "stock_vbmeta_sha256": sha(vbmeta),
        "final_bytes": len(rb), "final_sha256": sha(rb),
        "header_fields": {
            "kernel_size": len(kernel), "ramdisk_size": 0, "os_version": hex(osv),
            "header_size": hsize, "header_version": hver,
            "reserved": list(struct.unpack_from("<4I", hdr, 24)),
            "page_size": V4_PAGE,
            "note": "stock header page byte-copied; only kernel_size/ramdisk_size rewritten (stock ramdisk_size=1455342 kept no payload; zeroed for container consistency)",
        },
        "footer_fields": {"version": fver, "original_size": orig, "vbmeta_offset": voff, "vbmeta_size": vsz},
        "dtb": "none (vendor_boot DTB carries ABL runtime fixups)",
    }
    line = json.dumps(report, indent=2)
    if a.report:
        a.report.write_text(line + "\n")
    print(line)

if __name__ == "__main__":
    main()
