#!/usr/bin/env python3
"""Wave 15: extract UFS-related nodes (ufshc, ufsphy, and their clock/reset/interrupt/reg
wiring) from a flattened device tree. Read-only; prints a full parameter dump.
usage: python3 fdt_ufs_nodes.py DTB [DTB ...]
"""
import struct
import sys


def nodes_of(blob):
    if blob[:4] != b'\xd0\x0d\xfe\xed':
        sys.exit('not a flattened device tree')
    off_struct, off_strings = struct.unpack('>II', blob[8:16])
    size_strings, = struct.unpack('>I', blob[32:36])
    strings = blob[off_strings:off_strings + size_strings]
    out, path, at = {}, [], off_struct
    while True:
        token, = struct.unpack('>I', blob[at:at + 4])
        at += 4
        if token == 1:
            end = blob.index(b'\0', at)
            path.append(blob[at:end].decode())
            at = (end + 4) & ~3
            out['/'.join(path)] = {}
        elif token == 2:
            path.pop()
        elif token == 3:
            length, name_off = struct.unpack('>II', blob[at:at + 8])
            at += 8
            name = strings[name_off:strings.index(b'\0', name_off)].decode()
            out['/'.join(path)][name] = blob[at:at + length]
            at = (at + length + 3) & ~3
        elif token == 9:
            return out
        elif token != 4:
            sys.exit(f'unexpected token {token}')


def u32s(value):
    n = len(value) // 4
    return list(struct.unpack(f'>{n}I', value[:n * 4]))


def cells_of(nodes, path, what, default):
    parent = path.rsplit('/', 1)[0] or '/'
    v = nodes.get(parent, {}).get(what)
    if v and len(v) == 4:
        return struct.unpack('>I', v)[0]
    return default


def decode_reg(nodes, path, props):
    reg = props.get('reg')
    if not reg:
        return None
    a = cells_of(nodes, path, '#address-cells', 2)
    s = cells_of(nodes, path, '#size-cells', 2)
    words = u32s(reg)
    out, i = [], 0
    while i + a + s <= len(words):
        base = 0
        for w in words[i:i + a]:
            base = base << 32 | w
        size = 0
        for w in words[i + a:i + a + s]:
            size = size << 32 | w
        out.append((base, size))
        i += a + s
    return out


def fmt_props(nodes, path):
    props = nodes[path]
    lines = []
    for name in sorted(props):
        v = props[name]
        if name == 'reg':
            regs = decode_reg(nodes, path, props)
            if regs:
                lines.append('    reg: ' + '; '.join(f'0x{b:x}+0x{s:x}' for b, s in regs))
        elif name in ('clocks', 'clock-names', 'resets', 'reset-names',
                      'interrupts', 'interrupt-names', 'compatible', 'status'):
            if name in ('clock-names', 'reset-names', 'interrupt-names', 'compatible', 'status'):
                lines.append(f'    {name}: {v.rstrip(b(chr(0))).decode(errors="replace")!r}'
                             if False else f'    {name}: ' + v.split(b'\0')[0].decode(errors='replace')
                             + ('' if len(v) == v.index(b'\0') + 1 else
                                ' | '.join(x.decode(errors='replace') for x in v.split(b'\0') if x)))
            else:
                words = u32s(v)
                lines.append(f'    {name}: ' + ' '.join(f'0x{w:x}' for w in words))
        elif name in ('lanes-per-direction', 'max-mbps', 'freq-table-hz', 'vdd-hba-supply',
                      'vccq-supply', 'vcc-supply', 'vdda-pll-supply', 'vdda-phy-supply',
                      'qcom,host-clk-reg', 'limits-fifo-size', 'limits-dsd-ids', 'limits-hs-ids'):
            words = u32s(v) if len(v) % 4 == 0 else []
            lines.append(f'    {name}: ' + (' '.join(str(w) for w in words) if words else repr(v)))
    return '\n'.join(lines)


b = bytes


def main():
    for dtb in sys.argv[1:]:
        blob = open(dtb, 'rb').read()
        nodes = nodes_of(blob)
        print(f'==== {dtb}: {len(nodes)} nodes')
        hits = []
        for path in nodes:
            low = path.lower()
            props = nodes[path]
            compat = props.get('compatible', b'').split(b'\0')[0].decode(errors='replace')
            if any(k in low for k in ('ufs', 'ufshc', 'ufsphy')) or \
               any(k in compat.lower() for k in ('ufs', 'phy-qcom-ufs')):
                hits.append((path, compat))
        for path, compat in sorted(hits):
            print(f'  NODE {path}')
            print(f'    compatible: {compat}')
            print(fmt_props(nodes, path))
        # the scsi/channel nodes hanging off ufshc
        for path in sorted(nodes):
            if 'ufs' in path.lower() and path.count('/') >= 3:
                pass
        # aliases and chosen for ufs
        for path in ('/aliases', '/chosen'):
            if path in nodes:
                for k, v in nodes[path].items():
                    if 'ufs' in k.lower() or b'ufs' in v.lower():
                        print(f'  {path}:{k} = {v.split(b"\0")[0].decode(errors="replace")}')


if __name__ == '__main__':
    main()
