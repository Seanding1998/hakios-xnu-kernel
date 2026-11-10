import sys, hashlib

raw = open(sys.argv[1], 'rb').read()
print('sha256:', hashlib.sha256(raw).hexdigest())
# the kernel log section markers used by the loader (Wave7b klogdump)
start = raw.find(b'== KERNEL LOG ==')
end = raw.find(b'== END OF LOG ==')
print('KERNEL LOG marker at', start, 'END OF LOG at', end)
if start >= 0:
    stop = end + len(b'== END OF LOG ==') if end >= 0 else len(raw)
    seg = raw[start:stop]
    txt = seg.decode('utf-8', 'replace')
    out = sys.argv[2]
    open(out, 'w', encoding='utf-8').write(txt)
    print('extracted', len(seg), 'raw bytes ->', out)
    print('---- first 600 chars ----')
    print(txt[:600])
    print('---- last 400 chars ----')
    print(txt[-400:])
else:
    print('no kernel log marker; first 256 bytes:', raw[:256])
