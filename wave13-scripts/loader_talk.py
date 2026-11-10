#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""loader_talk.py - Wave 13: host-side USB talk tool for the xnuloader gadget.

Pure Windows-side tool. Drives the loader USB command server (VID:PID
18d1:d00d, product/serial "xnuloader", bulk, pure-ASCII protocol) through
libusb-1.0.dll loaded via ctypes -- no pyusb dependency.

Protocol (from ~/hakios/kernel/xnuloader/loader.c:3960-4035, Wave-13 brief):
  commands : getvar, oem log, oem screenshot, oem run[:checkpoint],
             upload, download:<hex>, oem clearscreen, reboot ...
  replies  : OKAY / FAIL:<reason> / DATA<hexlen> followed by <hexlen> bytes

Modes:
  list              enumerate USB devices visible to libusb (WinUSB/libusbK/
                    libusb0-bound devices only -- the Windows backend skips
                    devices bound to usbccgp/HID/vendor drivers)
  probe             find 18d1:d00d, print descriptors, open + claim interface
                    (the key Wave-13 validation: does libusb work over a
                    Zadig WinUSB binding?)
  cmd <ascii>       send one ASCII command on bulk-OUT, receive and parse the
                    reply frame from bulk-IN
  log               send "oem log", save the DATA payload to a file
  dllinfo           print libusb runtime version / backend info
  selftest          protocol-parser unit tests + safe no-device DLL checks

Examples:
  python loader_talk.py list
  python loader_talk.py probe
  python loader_talk.py cmd getvar
  python loader_talk.py cmd "oem log" --timeout 5000
  python loader_talk.py log --out oem-log.out
  python loader_talk.py selftest

Exit codes: 0 ok, 1 device/protocol failure, 2 usage, 3 selftest failure.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DLL = os.path.join(REPO, "intel", "usb-driver", "libusb-1.0.dll")

TARGET_VID = 0x18D1
TARGET_PID = 0xD00D

# ---------------------------------------------------------------- libusb ABI

LIBUSB_SUCCESS = 0
LIBUSB_CLASS_PER_INTERFACE = 0
LIBUSB_TRANSFER_TYPE_BULK = 2
LIBUSB_ENDPOINT_IN = 0x80
LIBUSB_ENDPOINT_DIR_MASK = 0x80
LIBUSB_TRANSFER_TYPE_MASK = 0x03

LIBUSB_CAP_HAS_CAPABILITY = 0x0000

ERROR_NAMES = {
    0: "LIBUSB_SUCCESS", -1: "LIBUSB_ERROR_IO", -2: "LIBUSB_ERROR_INVALID_PARAM",
    -3: "LIBUSB_ERROR_ACCESS", -4: "LIBUSB_ERROR_NO_DEVICE",
    -5: "LIBUSB_ERROR_NOT_FOUND", -6: "LIBUSB_ERROR_BUSY",
    -7: "LIBUSB_ERROR_TIMEOUT", -8: "LIBUSB_ERROR_OVERFLOW",
    -9: "LIBUSB_ERROR_PIPE", -10: "LIBUSB_ERROR_INTERRUPTED",
    -11: "LIBUSB_ERROR_NO_MEM", -12: "LIBUSB_ERROR_NOT_SUPPORTED",
    -99: "LIBUSB_ERROR_OTHER",
}

SPEED_NAMES = {
    0: "unknown", 1: "low", 2: "full", 3: "high", 4: "super", 5: "super+",
}

CLASS_NAMES = {
    0x00: "per-interface", 0x02: "comm", 0x03: "hid", 0x08: "msc",
    0x09: "hub", 0x0E: "video", 0x10: "audio/video", 0xE0: "wireless",
    0xEF: "misc", 0xFF: "vendor",
}


def class_name(c):
    return CLASS_NAMES.get(c, "0x%02x" % c)


class LibusbVersion(ctypes.Structure):
    _fields_ = [
        ("major", ctypes.c_uint16),
        ("minor", ctypes.c_uint16),
        ("micro", ctypes.c_uint16),
        ("nano", ctypes.c_uint16),
        ("rc", ctypes.c_char_p),
        ("describe", ctypes.c_char_p),
    ]


class DeviceDescriptor(ctypes.Structure):
    # Natural (non-packed) layout; 18 bytes, no padding needed on x64.
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bcdUSB", ctypes.c_uint16),
        ("bDeviceClass", ctypes.c_uint8),
        ("bDeviceSubClass", ctypes.c_uint8),
        ("bDeviceProtocol", ctypes.c_uint8),
        ("bMaxPacketSize0", ctypes.c_uint8),
        ("idVendor", ctypes.c_uint16),
        ("idProduct", ctypes.c_uint16),
        ("bcdDevice", ctypes.c_uint16),
        ("iManufacturer", ctypes.c_uint8),
        ("iProduct", ctypes.c_uint8),
        ("iSerialNumber", ctypes.c_uint8),
        ("bNumConfigurations", ctypes.c_uint8),
    ]


class EndpointDescriptor(ctypes.Structure):
    # Natural x64 layout: 9 raw bytes, pad 7, extra ptr @16, int @24, size 32.
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bEndpointAddress", ctypes.c_uint8),
        ("bmAttributes", ctypes.c_uint8),
        ("wMaxPacketSize", ctypes.c_uint16),
        ("bInterval", ctypes.c_uint8),
        ("bRefresh", ctypes.c_uint8),
        ("bSynchAddress", ctypes.c_uint8),
        ("extra", ctypes.POINTER(ctypes.c_ubyte)),
        ("extra_length", ctypes.c_int),
    ]


class InterfaceDescriptor(ctypes.Structure):
    # Natural x64 layout: 9 raw bytes, pad 7, endpoint ptr @16, size 40.
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("bInterfaceNumber", ctypes.c_uint8),
        ("bAlternateSetting", ctypes.c_uint8),
        ("bNumEndpoints", ctypes.c_uint8),
        ("bInterfaceClass", ctypes.c_uint8),
        ("bInterfaceSubClass", ctypes.c_uint8),
        ("bInterfaceProtocol", ctypes.c_uint8),
        ("iInterface", ctypes.c_uint8),
        ("endpoint", ctypes.POINTER(EndpointDescriptor)),
        ("extra", ctypes.POINTER(ctypes.c_ubyte)),
        ("extra_length", ctypes.c_int),
    ]


class Interface(ctypes.Structure):
    _fields_ = [
        ("altsetting", ctypes.POINTER(InterfaceDescriptor)),
        ("num_altsetting", ctypes.c_int),
    ]


class ConfigDescriptor(ctypes.Structure):
    # Natural x64 layout: 9 raw bytes, pad to 16 for interface ptr, size 40.
    _fields_ = [
        ("bLength", ctypes.c_uint8),
        ("bDescriptorType", ctypes.c_uint8),
        ("wTotalLength", ctypes.c_uint16),
        ("bNumInterfaces", ctypes.c_uint8),
        ("bConfigurationValue", ctypes.c_uint8),
        ("iConfiguration", ctypes.c_uint8),
        ("bmAttributes", ctypes.c_uint8),
        ("MaxPower", ctypes.c_uint8),
        ("interface", ctypes.POINTER(Interface)),
        ("extra", ctypes.POINTER(ctypes.c_ubyte)),
        ("extra_length", ctypes.c_int),
    ]


class Libusb(object):
    """Minimal ctypes binding for libusb-1.0.dll (1.0.2x, x64)."""

    def __init__(self, dll_path=DEFAULT_DLL, debug=0):
        if not os.path.isfile(dll_path):
            raise SystemExit("libusb DLL not found: %s" % dll_path)
        dll_dir = os.path.dirname(os.path.abspath(dll_path))
        try:
            os.add_dll_directory(dll_dir)  # py3.8+: keep dependency resolution local
        except (AttributeError, OSError):
            pass  # the DLL loads by absolute path below; libusb deps are system DLLs

        self.dll = ctypes.CDLL(os.path.abspath(dll_path))
        d = self.dll
        P = ctypes.POINTER

        d.libusb_get_version.restype = P(LibusbVersion)
        d.libusb_get_version.argtypes = []

        d.libusb_init.restype = ctypes.c_int
        d.libusb_init.argtypes = [P(ctypes.c_void_p)]  # libusb_context** via byref(c_void_p)

        d.libusb_exit.restype = None
        d.libusb_exit.argtypes = [ctypes.c_void_p]

        d.libusb_set_option.restype = ctypes.c_int  # variadic: no argtypes

        d.libusb_get_device_list.restype = ctypes.c_ssize_t
        d.libusb_get_device_list.argtypes = [ctypes.c_void_p, P(P(P(ctypes.c_void_p)))]

        d.libusb_free_device_list.restype = None
        d.libusb_free_device_list.argtypes = [P(P(ctypes.c_void_p)), ctypes.c_int]

        d.libusb_get_device_descriptor.restype = ctypes.c_int
        d.libusb_get_device_descriptor.argtypes = [ctypes.c_void_p, P(DeviceDescriptor)]

        d.libusb_get_active_config_descriptor.restype = ctypes.c_int
        d.libusb_get_active_config_descriptor.argtypes = [ctypes.c_void_p, P(P(ConfigDescriptor))]

        d.libusb_free_config_descriptor.restype = None
        d.libusb_free_config_descriptor.argtypes = [P(ConfigDescriptor)]

        d.libusb_get_bus_number.restype = ctypes.c_uint8
        d.libusb_get_bus_number.argtypes = [ctypes.c_void_p]

        d.libusb_get_device_address.restype = ctypes.c_uint8
        d.libusb_get_device_address.argtypes = [ctypes.c_void_p]

        d.libusb_get_device_speed.restype = ctypes.c_int
        d.libusb_get_device_speed.argtypes = [ctypes.c_void_p]

        d.libusb_get_port_numbers.restype = ctypes.c_int
        d.libusb_get_port_numbers.argtypes = [ctypes.c_void_p, P(ctypes.c_uint8), ctypes.c_int]

        d.libusb_get_parent.restype = ctypes.c_void_p
        d.libusb_get_parent.argtypes = [ctypes.c_void_p]

        d.libusb_open.restype = ctypes.c_int
        d.libusb_open.argtypes = [ctypes.c_void_p, P(ctypes.c_void_p)]

        d.libusb_close.restype = None
        d.libusb_close.argtypes = [ctypes.c_void_p]

        d.libusb_claim_interface.restype = ctypes.c_int
        d.libusb_claim_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]

        d.libusb_release_interface.restype = ctypes.c_int
        d.libusb_release_interface.argtypes = [ctypes.c_void_p, ctypes.c_int]

        d.libusb_kernel_driver_active.restype = ctypes.c_int
        d.libusb_kernel_driver_active.argtypes = [ctypes.c_void_p, ctypes.c_int]

        d.libusb_set_configuration.restype = ctypes.c_int
        d.libusb_set_configuration.argtypes = [ctypes.c_void_p, ctypes.c_int]

        d.libusb_bulk_transfer.restype = ctypes.c_int
        d.libusb_bulk_transfer.argtypes = [ctypes.c_void_p, ctypes.c_uint8,
                                           P(ctypes.c_ubyte), ctypes.c_int,
                                           P(ctypes.c_int), ctypes.c_uint]

        d.libusb_get_string_descriptor_ascii.restype = ctypes.c_int
        d.libusb_get_string_descriptor_ascii.argtypes = [ctypes.c_void_p, ctypes.c_uint8,
                                                         P(ctypes.c_ubyte), ctypes.c_int]

        d.libusb_error_name.restype = ctypes.c_char_p
        d.libusb_error_name.argtypes = [ctypes.c_int]

        d.libusb_has_capability.restype = ctypes.c_int
        d.libusb_has_capability.argtypes = [ctypes.c_uint32]

        self.ctx = ctypes.c_void_p()
        if debug:
            # LIBUSB_OPTION_LOG_LEVEL = 0; set before init via default-context list
            d.libusb_set_option(None, 0, ctypes.c_int(debug))
        r = d.libusb_init(ctypes.byref(self.ctx))
        if r != LIBUSB_SUCCESS:
            raise SystemExit("libusb_init failed: %s" % self.errname(r))
        self._inited = True

    # -- helpers ---------------------------------------------------------

    def errname(self, code):
        try:
            s = self.dll.libusb_error_name(code)
            if s:
                return s.decode("ascii", "replace")
        except Exception:
            pass
        return ERROR_NAMES.get(code, "errno=%d" % code)

    def version(self):
        v = self.dll.libusb_get_version().contents
        rc = (v.rc or b"").decode("ascii", "replace")
        return "%d.%d.%d.%d%s" % (v.major, v.minor, v.micro, v.nano, rc)

    def close(self):
        if self._inited:
            self.dll.libusb_exit(self.ctx)
            self._inited = False

    def device_list(self):
        """Return (list-of-device-void_p). Caller must call free_list."""
        plist = ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))()
        n = self.dll.libusb_get_device_list(self.ctx, ctypes.byref(plist))
        if n < 0:
            raise SystemExit("libusb_get_device_list failed: %s" % self.errname(n))
        return plist, n

    def free_list(self, plist, n, unref=1):
        self.dll.libusb_free_device_list(plist, unref)

    def device_desc(self, dev):
        desc = DeviceDescriptor()
        r = self.dll.libusb_get_device_descriptor(dev, ctypes.byref(desc))
        if r != LIBUSB_SUCCESS:
            return None
        return desc

    def port_path(self, dev):
        buf = (ctypes.c_uint8 * 16)()
        n = self.dll.libusb_get_port_numbers(dev, buf, 16)
        if n < 0:
            return "?"
        return "-".join("%d" % buf[i] for i in range(n))

    def strings(self, dev, desc):
        """Open the device and read manufacturer/product/serial (may fail)."""
        out = {"manufacturer": None, "product": None, "serial": None}
        h = ctypes.c_void_p()
        r = self.dll.libusb_open(dev, ctypes.byref(h))
        if r != LIBUSB_SUCCESS:
            out["error"] = self.errname(r)
            return out
        for key, idx in (("manufacturer", desc.iManufacturer),
                         ("product", desc.iProduct),
                         ("serial", desc.iSerialNumber)):
            if not idx:
                continue
            buf = (ctypes.c_ubyte * 256)()
            n = self.dll.libusb_get_string_descriptor_ascii(
                h, idx, buf, 256)
            if n > 0:
                out[key] = bytes(buf[:n]).decode("utf-8", "replace")
        self.dll.libusb_close(h)
        return out


# ------------------------------------------------------------ protocol layer

class Response(object):
    """Parsed loader reply."""

    def __init__(self, status, payload=None, raw=b""):
        self.status = status          # "OKAY" | "FAIL" | "DATA" | "PARTIAL"
        self.payload = payload        # bytes for DATA, ascii text for OKAY/FAIL
        self.raw = raw                # raw bytes seen so far (for forensics)

    def __eq__(self, other):
        if not isinstance(other, Response):
            return NotImplemented
        # raw bytes are forensics, not semantics: compare status+payload only
        return (self.status == other.status and
                self.payload == other.payload)

    def __repr__(self):
        return "Response(status=%s, payload=%r)" % (
            self.status,
            (self.payload[:80] + b"...") if self.payload and len(self.payload) > 80
            else self.payload,
        )


def _hex_prefix(data, start):
    """Consume hex digits at data[start:]; return (length, end_index, valid)."""
    i = start
    n = len(data)
    while i < n and data[i:i + 1] in b"0123456789abcdefABCDEF":
        i += 1
    if i == start:
        return None, start, False
    try:
        return int(data[start:i], 16), i, True
    except ValueError:
        return None, start, False


def _clean_text(payload):
    """Trim trailing CR/LF/space from an ASCII tail."""
    return payload.rstrip(b"\r\n \t")


class LoaderProto(object):
    """Incremental wire parser for xnuloader replies.

    feed(b) -> None while the frame is incomplete, Response(...) when done.
    Accepted frames (first byte stream):
        OKAY                       -> Response("OKAY", None)
        OKAY<text>                 -> Response("OKAY", <text>)   (getvar style)
        FAIL:<reason>              -> Response("FAIL", reason)
        DATA<hexlen><payload...>   -> Response("DATA", payload)  (payload may
                                      span several feed() calls)
    Garbage input never raises; it surfaces as Response("PARTIAL") with the
    raw bytes so the caller can log and keep the session alive.
    """

    def __init__(self):
        self.buf = b""
        self.state = "header"   # header -> data-payload | done
        self.want = None

    def feed(self, data):
        if data:
            self.buf += data
        return self._parse()

    def flush(self):
        """Finalize with whatever is buffered (used at read-timeout)."""
        return self._parse() if self.buf else None

    def _parse(self):
        if self.state == "data-payload":
            if len(self.buf) >= self.want:
                payload = self.buf[:self.want]
                self.buf = self.buf[self.want:]
                self.state = "done"
                return Response("DATA", payload, raw=payload)
            return None

        if not self.buf:
            return None

        # Wait for more bytes while buf is a PROPER prefix of a frame header
        # (e.g. b"OK", b"FAIL", b"DATA0"). b"OKAY" itself is a full frame.
        for cand in (b"OKAY", b"FAIL:", b"DATA"):
            if len(self.buf) < len(cand) and cand.startswith(self.buf):
                return None

        if self.buf.startswith(b"OKAY"):
            tail = _clean_text(self.buf[4:])
            self.state = "done"
            self.buf = b""
            return Response("OKAY", tail if tail else None,
                            raw=(b"OKAY" + tail))
        if self.buf.startswith(b"FAIL:"):
            tail = _clean_text(self.buf[5:])
            self.state = "done"
            self.buf = b""
            return Response("FAIL", tail, raw=(b"FAIL:" + tail))
        if self.buf.startswith(b"DATA"):
            length, end, valid = _hex_prefix(self.buf, 4)
            if not valid:
                # "DATA" without a hex length: surface raw, do not wedge.
                self.state = "done"
                self.buf = b""
                return Response("PARTIAL", None, raw=self.buf)
            self.buf = self.buf[end:]
            self.want = length
            self.state = "data-payload"
            return self._parse()
        self.state = "done"
        resp = Response("PARTIAL", None, raw=self.buf)
        self.buf = b""
        return resp

    @staticmethod
    def encode_command(ascii_cmd, newline=False):
        """Wire encoding of a command: pure ASCII, no terminator by default."""
        data = ascii_cmd.encode("ascii", "strict")
        if newline:
            data += b"\n"
        return data


# ----------------------------------------------------------------- device ops

def pick_iface_eps(cfg):
    """Pick (iface_number, ep_out, ep_in, iface_desc): first interface with a
    bulk OUT and a bulk IN endpoint."""
    for i in range(cfg.bNumInterfaces):
        for a in range(cfg.interface[i].num_altsetting):
            ifd = cfg.interface[i].altsetting[a]
            ep_out = ep_in = None
            for e in range(ifd.bNumEndpoints):
                ep = ifd.endpoint[e]
                if (ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK) != LIBUSB_TRANSFER_TYPE_BULK:
                    continue
                if ep.bEndpointAddress & LIBUSB_ENDPOINT_DIR_MASK:
                    ep_in = ep_in or ep.bEndpointAddress
                else:
                    ep_out = ep_out or ep.bEndpointAddress
            if ep_out is not None and ep_in is not None:
                return ifd.bInterfaceNumber, ep_out, ep_in, ifd
    return None, None, None, None


def describe_config(cfg):
    lines = []
    lines.append("config %d: %d interface(s), wTotalLength=%d, bmAttributes=0x%02x, MaxPower=%dmA(x2)" % (
        cfg.bConfigurationValue, cfg.bNumInterfaces, cfg.wTotalLength,
        cfg.bmAttributes, cfg.MaxPower))
    for i in range(cfg.bNumInterfaces):
        for a in range(cfg.interface[i].num_altsetting):
            ifd = cfg.interface[i].altsetting[a]
            lines.append(
                "  if%02d alt%d class=%s subclass=0x%02x proto=0x%02x endpoints=%d" % (
                    ifd.bInterfaceNumber, ifd.bAlternateSetting,
                    class_name(ifd.bInterfaceClass), ifd.bInterfaceSubClass,
                    ifd.bInterfaceProtocol, ifd.bNumEndpoints))
            for e in range(ifd.bNumEndpoints):
                ep = ifd.endpoint[e]
                dirn = "IN " if ep.bEndpointAddress & LIBUSB_ENDPOINT_DIR_MASK else "OUT"
                ttype = ("bulk" if (ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK)
                         == LIBUSB_TRANSFER_TYPE_BULK else
                         ("ctrl" if (ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK) == 0
                          else "0x%02x" % (ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK)))
                lines.append("    ep 0x%02x %s %-4s maxpkt=%d interval=%d" % (
                    ep.bEndpointAddress, dirn, ttype, ep.wMaxPacketSize, ep.bInterval))
    return "\n".join(lines)


def do_list(lib, args):
    plist, n = lib.device_list()
    print("libusb %s sees %d device(s) (Windows backend lists only "
          "WinUSB/libusbK/libusb0-bound devices):" % (lib.version(), n))
    found = 0
    for i in range(n):
        dev = plist[i]
        desc = lib.device_desc(dev)
        if not desc:
            print("  [%d] <descriptor read failed>" % i)
            continue
        speed = lib.dll.libusb_get_device_speed(dev)
        loc = "bus %d port %s addr %d" % (
            lib.dll.libusb_get_bus_number(dev), lib.port_path(dev),
            lib.dll.libusb_get_device_address(dev))
        core = "  %s  %04x:%04x  class=%s  bcdUSB=%04x bcdDevice=%04x  speed=%s" % (
            loc, desc.idVendor, desc.idProduct,
            class_name(desc.bDeviceClass), desc.bcdUSB, desc.bcdDevice,
            SPEED_NAMES.get(speed, str(speed)))
        found += 1
        strs = lib.strings(dev, desc)
        tag = ""
        if strs.get("product") or strs.get("manufacturer") or strs.get("serial"):
            tag = "  | " + " / ".join(
                "%s" % strs[k] for k in ("manufacturer", "product", "serial")
                if strs.get(k))
        marker = "   <== LOADER GADGET" if (desc.idVendor == TARGET_VID and
                                            desc.idProduct == TARGET_PID) else ""
        print(core + tag + marker)
        if "error" in strs:
            print("       (string read failed: %s)" % strs["error"])
    lib.free_list(plist, n)
    if not n:
        print("  (none)")
    return 0


def open_and_claim(lib, dev, desc, iface=None):
    """Open device + claim interface; returns (handle, cfg, iface, ep_out, ep_in)
    or raises DeviceError with the libusb error text."""
    h = ctypes.c_void_p()
    r = lib.dll.libusb_open(dev, ctypes.byref(h))
    if r != LIBUSB_SUCCESS:
        raise DeviceError("libusb_open failed: %s" % lib.errname(r))
    cfg = ctypes.POINTER(ConfigDescriptor)()
    r = lib.dll.libusb_get_active_config_descriptor(dev, ctypes.byref(cfg))
    if r != LIBUSB_SUCCESS:
        lib.dll.libusb_close(h)
        raise DeviceError("libusb_get_active_config_descriptor failed: %s"
                          % lib.errname(r))
    if iface is None:
        iface, ep_out, ep_in, ifd = pick_iface_eps(cfg.contents)
        if iface is None:
            print(describe_config(cfg.contents))
            lib.dll.libusb_free_config_descriptor(cfg)
            lib.dll.libusb_close(h)
            raise DeviceError("no interface with bulk OUT+IN pair found")
    else:
        ifd = find_iface_desc(cfg.contents, iface)
        ep_out, ep_in = scan_eps_for_iface(cfg.contents, iface)
        if ep_out is None and ep_in is None:
            lib.dll.libusb_free_config_descriptor(cfg)
            lib.dll.libusb_close(h)
            raise DeviceError("interface %d has no bulk endpoints" % iface)
    r = lib.dll.libusb_claim_interface(h, iface)
    if r != LIBUSB_SUCCESS:
        print(describe_config(cfg.contents))
        lib.dll.libusb_free_config_descriptor(cfg)
        lib.dll.libusb_close(h)
        raise DeviceError("libusb_claim_interface(if%d) failed: %s  <-- key "
                          "Wave-13 datapoint" % (iface, lib.errname(r)))
    return h, cfg, iface, ep_out, ep_in, ifd


def find_iface_desc(cfg, iface):
    """Return the first altsetting InterfaceDescriptor for iface (or None)."""
    for i in range(cfg.bNumInterfaces):
        for a in range(cfg.interface[i].num_altsetting):
            ifd = cfg.interface[i].altsetting[a]
            if ifd.bInterfaceNumber == iface:
                return ifd
    return None


def scan_eps_for_iface(cfg, iface):
    ep_out = ep_in = None
    for i in range(cfg.bNumInterfaces):
        for a in range(cfg.interface[i].num_altsetting):
            ifd = cfg.interface[i].altsetting[a]
            if ifd.bInterfaceNumber != iface:
                continue
            for e in range(ifd.bNumEndpoints):
                ep = ifd.endpoint[e]
                if (ep.bmAttributes & LIBUSB_TRANSFER_TYPE_MASK) != LIBUSB_TRANSFER_TYPE_BULK:
                    continue
                if ep.bEndpointAddress & LIBUSB_ENDPOINT_DIR_MASK:
                    ep_in = ep_in or ep.bEndpointAddress
                else:
                    ep_out = ep_out or ep.bEndpointAddress
    return ep_out, ep_in


class DeviceError(Exception):
    pass


def connect(lib, args):
    """Locate + open + claim the gadget. Returns session dict."""
    vid = int(args.vid, 16) if args.vid else TARGET_VID
    pid = int(args.pid, 16) if args.pid else TARGET_PID
    dev = desc = None
    plist, n = lib.device_list()
    try:
        for i in range(n):
            d = lib.device_desc(plist[i])
            if d and d.idVendor == vid and d.idProduct == pid:
                dev, desc = plist[i], d
                break
    finally:
        lib.free_list(plist, n)
    if dev is None:
        raise DeviceError(
            "device %04x:%04x not found on this bus (expected: it only "
            "enumerates when the phone runs the loader/usbmode image; in "
            "Android it shows as 22d9:2765 ADB, in stock bootloader as "
            "18d1:d00d 'Android' fastboot)" % (vid, pid))
    speed = lib.dll.libusb_get_device_speed(dev)
    loc = "bus %d port %s addr %d speed=%s" % (
        lib.dll.libusb_get_bus_number(dev), lib.port_path(dev),
        lib.dll.libusb_get_device_address(dev), SPEED_NAMES.get(speed, speed))
    print("device %04x:%04x @ %s" % (vid, pid, loc))
    strs = lib.strings(dev, desc)
    for k in ("manufacturer", "product", "serial"):
        if strs.get(k):
            print("  %s: %r" % (k, strs[k]))
    if "error" in strs:
        print("  (string read: %s)" % strs["error"])
    print("  bcdUSB=%04x bDeviceClass=%s bMaxPacketSize0=%d configs=%d" % (
        desc.bcdUSB, class_name(desc.bDeviceClass), desc.bMaxPacketSize0,
        desc.bNumConfigurations))
    h, cfg, iface, ep_out, ep_in, ifd = open_and_claim(lib, dev, desc, args.iface)
    print("  OPEN+CLAIM OK (interface %d, class=%s)" % (
        iface, class_name(ifd.bInterfaceClass) if ifd else "?"))
    print(describe_config(cfg.contents))
    return {"handle": h, "cfg": cfg, "iface": iface,
            "ep_out": ep_out, "ep_in": ep_in,
            "maxpkt": (ifd.endpoint[0].wMaxPacketSize
                       if ifd and ifd.bNumEndpoints else 512)}


def disconnect(lib, sess):
    lib.dll.libusb_release_interface(sess["handle"], sess["iface"])
    lib.dll.libusb_free_config_descriptor(sess["cfg"])
    lib.dll.libusb_close(sess["handle"])


def do_probe(lib, args):
    sess = connect(lib, args)
    print("probe verdict: libusb opens and claims the WinUSB-bound gadget; "
          "bulk endpoints as listed above")
    disconnect(lib, sess)
    return 0


def bulk_in(lib, sess, timeout_ms, deadline=None):
    """One bulk-IN read; returns (bytes, transferred, errname-or-None)."""
    size = max(sess.get("maxpkt", 512), 4096)
    buf = (ctypes.c_ubyte * size)()
    transferred = ctypes.c_int(0)
    r = lib.dll.libusb_bulk_transfer(sess["handle"], sess["ep_in"], buf, size,
                                     ctypes.byref(transferred), timeout_ms)
    data = bytes(buf[:transferred.value]) if transferred.value > 0 else b""
    return data, transferred.value, (None if r == 0 else lib.errname(r))


def do_cmd(lib, args):
    sess = connect(lib, args)
    try:
        resp = transact(lib, sess, args.command, args.timeout,
                        newline=args.nl, quiet=True)
        if resp is None:
            print("NO RESPONSE (bulk-IN timeout after %d ms)" % args.timeout)
            return 1
        print("status : %s" % resp.status)
        if resp.payload is not None:
            if len(resp.payload) <= 256:
                print("payload: %r" % resp.payload)
            else:
                print("payload: %d bytes, first 256: %r" % (
                    len(resp.payload), resp.payload[:256]))
        if resp.status == "PARTIAL":
            print("raw    : %r" % resp.raw)
            return 1
        return 0 if resp.status == "OKAY" else 1
    finally:
        disconnect(lib, sess)


def transact(lib, sess, command, timeout_ms, newline=False, quiet=False):
    """Send one ASCII command, collect the reply frame. Returns Response|None."""
    wire = LoaderProto.encode_command(command, newline)
    if not quiet:
        print(">> %r (%d bytes -> ep 0x%02x)" % (wire, len(wire), sess["ep_out"]))
    transferred = ctypes.c_int(0)
    outbuf = (ctypes.c_ubyte * len(wire)).from_buffer_copy(wire)
    r = lib.dll.libusb_bulk_transfer(sess["handle"], sess["ep_out"], outbuf,
                                     len(wire), ctypes.byref(transferred),
                                     timeout_ms)
    if r != LIBUSB_SUCCESS or transferred.value != len(wire):
        raise DeviceError("bulk-OUT failed: %s (%d/%d bytes)"
                          % (lib.errname(r), transferred.value, len(wire)))
    parser = LoaderProto()
    end = time.time() + timeout_ms / 1000.0
    while True:
        remain = int((end - time.time()) * 1000)
        if remain <= 0:
            partial = parser.flush()
            if partial:
                return partial
            return None
        data, n, err = bulk_in(lib, sess, remain)
        if n > 0:
            if not quiet:
                print("<< + %d bytes: %r" % (n, data[:64]))
            resp = parser.feed(data)
            if resp is not None:
                return resp
            continue
        if err and "TIMEOUT" in str(err):
            continue
        if err:
            raise DeviceError("bulk-IN failed: %s" % err)
        return None


def do_log(lib, args):
    sess = connect(lib, args)
    try:
        resp = transact(lib, sess, "oem log", args.timeout)
        if resp is None:
            print("NO RESPONSE to 'oem log'")
            return 1
        if resp.status == "DATA" and resp.payload is not None:
            out = args.out or os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "oem-log.out")
            with open(out, "wb") as f:
                f.write(resp.payload)
            print("saved %d bytes -> %s" % (len(resp.payload), out))
            print(resp.payload[:400].decode("utf-8", "replace"))
            return 0
        print("unexpected reply: %s payload=%r raw=%r" % (
            resp.status, resp.payload, resp.raw[:200]))
        return 1
    finally:
        disconnect(lib, sess)


def do_dllinfo(lib, args):
    v = lib.version()
    caps = lib.dll.libusb_has_capability(LIBUSB_CAP_HAS_CAPABILITY)
    print("dll            : %s" % args.dll)
    print("libusb version : %s" % v)
    print("HAS_CAPABILITY : %s" % ("yes" if caps == 1 else "no (%s)" % caps))
    plist, n = lib.device_list()
    lib.free_list(plist, n)
    print("device-list    : OK (%d devices visible)" % n)
    print("backend        : Windows winusb/libusbK/libusb0 (UsbDk backend was "
          "removed from libusb 1.0.24+; USE_USBDK option is a no-op here)")
    return 0


# ------------------------------------------------------------------ selftest

def selftest(dll_path):
    """Protocol + safe no-device validation. Returns (passed, failed, log)."""
    log = []
    ok = fail = 0

    def check(name, cond, extra=""):
        nonlocal ok, fail
        if cond:
            ok += 1
            log.append("PASS %s %s" % (name, extra))
        else:
            fail += 1
            log.append("FAIL %s %s" % (name, extra))

    # ---- parser tests (no DLL needed)
    p = LoaderProto()
    check("parse.OKAY", p.feed(b"OKAY") == Response("OKAY", None))

    p = LoaderProto()
    check("parse.OKAY.value", p.feed(b"OKAYtaro\n") == Response("OKAY", b"taro"))

    p = LoaderProto()
    check("parse.FAIL", p.feed(b"FAIL:no such var") == Response("FAIL", b"no such var"))

    p = LoaderProto()
    check("parse.FAIL.prefix-wait",
          p.feed(b"FAIL") is None and
          p.feed(b":no such var") == Response("FAIL", b"no such var"))

    # Documented semantics: OKAY/FAIL complete at first chunk boundary (loader
    # sends each status line as one bulk write); DATA payloads are chunk-safe.

    payload = bytes(range(16))
    p = LoaderProto()
    r = p.feed(b"DATA" + b"%08x" % len(payload) + payload)
    check("parse.DATA.inline", r is not None and r.status == "DATA"
          and r.payload == payload, "len=%d" % (len(r.payload) if r else -1))

    p = LoaderProto()
    r = None
    r = p.feed(b"DATA" + b"%08x" % len(payload))
    check("parse.DATA.header-only", r is None)
    r = p.feed(payload[:5])
    check("parse.DATA.partial", r is None)
    r = p.feed(payload[5:])
    check("parse.DATA.chunked", r is not None and r.status == "DATA"
          and r.payload == payload)

    p = LoaderProto()
    r = p.feed(b"DATAzz")
    check("parse.DATA.badlen", r is not None and r.status == "PARTIAL")

    p = LoaderProto()
    r = p.feed(b"XXYZ")
    check("parse.garbage", r is not None and r.status == "PARTIAL")

    p = LoaderProto()
    check("parse.empty", p.feed(b"") is None)

    p = LoaderProto()
    check("parse.prefix.partial", p.feed(b"OK") is None and
          p.feed(b"AY") == Response("OKAY", None))

    p = LoaderProto()
    r = p.feed(b"OKAY")
    check("parse.OKAY.no-wedge", r == Response("OKAY", None))

    check("encode.getvar", LoaderProto.encode_command("getvar") == b"getvar")
    check("encode.nl", LoaderProto.encode_command("getvar", True) == b"getvar\n")
    check("encode.oem", LoaderProto.encode_command("oem log") == b"oem log")

    # fuzz: random bytes must never raise and always terminate the frame
    import random
    random.seed(13)
    fuzz_ok = True
    for _ in range(500):
        blob = bytes(random.randrange(256) for _ in range(random.randrange(1, 40)))
        q = LoaderProto()
        try:
            q.feed(blob)
        except Exception as e:
            fuzz_ok = False
            log.append("fuzz crash on %r: %r" % (blob, e))
            break
    check("parse.fuzz500", fuzz_ok, "(no exception, no wedge)")

    # ---- safe DLL checks (no device needed)
    try:
        lib = Libusb(dll_path)
        ver = lib.version()
        check("dll.load", True, "libusb %s" % ver)
        check("dll.version.shape",
              ver.startswith("1.0.") or ver.startswith("1.1."),
              ver)
        check("dll.init", lib._inited)
        plist, n = lib.device_list()
        lib.free_list(plist, n)
        check("dll.devicelist", n >= 0, "%d devices visible" % n)
        check("dll.errname", lib.errname(-7).endswith("TIMEOUT"),
              lib.errname(-7))
        caps = lib.dll.libusb_has_capability(LIBUSB_CAP_HAS_CAPABILITY)
        check("dll.capability", caps == 1, "caps=%d" % caps)
        lib.close()
        check("dll.exit", not lib._inited)
    except SystemExit as e:
        check("dll.load", False, str(e))
    except Exception as e:
        check("dll.load", False, repr(e))

    for line in log:
        print(line)
    print("selftest: %d passed, %d failed" % (ok, fail))
    return ok, fail


# ----------------------------------------------------------------------- CLI

def main(argv):
    ap = argparse.ArgumentParser(
        description="xnuloader USB gadget host tool (ctypes libusb, no pyusb)")
    ap.add_argument("--dll", default=os.environ.get(
        "LOADER_TALK_LIBUSB", DEFAULT_DLL), help="path to libusb-1.0.dll")
    ap.add_argument("--vid", help="target vendor id (hex, default 18d1)")
    ap.add_argument("--pid", help="target product id (hex, default d00d)")
    ap.add_argument("--iface", type=int, default=None,
                    help="interface number to claim (default: auto)")
    ap.add_argument("--timeout", type=int, default=2000,
                    help="transfer timeout in ms (default 2000)")
    ap.add_argument("--libusb-debug", type=int, default=0, metavar="0-4",
                    help="libusb log level")
    sub = ap.add_subparsers(dest="mode")

    sp_list = sub.add_parser("list", help="enumerate USB devices")
    sp_probe = sub.add_parser("probe", help="find+open+claim 18d1:d00d")
    sp_cmd = sub.add_parser("cmd", help="send one ASCII command")
    sp_cmd.add_argument("command", help="e.g. getvar | oem log | oem clearscreen")
    sp_cmd.add_argument("--nl", action="store_true",
                        help="append \\n to the command")
    sp_log = sub.add_parser("log", help="fetch 'oem log' payload to file")
    sp_log.add_argument("--out", help="output file (default oem-log.out)")
    sub.add_parser("dllinfo", help="print libusb runtime info")
    sp_self = sub.add_parser("selftest", help="parser tests + safe DLL checks")

    args = ap.parse_args(argv)
    if args.mode is None:
        ap.print_help()
        return 2

    if args.mode == "selftest":
        ok, fail = selftest(args.dll)
        return 3 if fail else 0

    lib = Libusb(args.dll, debug=args.libusb_debug)
    try:
        if args.mode == "list":
            return do_list(lib, args)
        if args.mode == "probe":
            return do_probe(lib, args)
        if args.mode == "cmd":
            return do_cmd(lib, args)
        if args.mode == "log":
            return do_log(lib, args)
        if args.mode == "dllinfo":
            return do_dllinfo(lib, args)
    except DeviceError as e:
        print("DEVICE ERROR: %s" % e)
        return 1
    finally:
        lib.close()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
