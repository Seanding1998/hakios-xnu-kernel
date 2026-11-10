import sys, hashlib

raw = open(sys.argv[1], 'rb').read()
out = sys.argv[2]
print('sha256:', hashlib.sha256(raw).hexdigest())
end = raw.find(b'== END OF LOG ==')
stop = end + len(b'== END OF LOG ==') if end >= 0 else len(raw)
txt = raw[:stop].decode('utf-8', 'replace')
open(out, 'w', encoding='utf-8').write(txt)
print('extracted', stop, 'bytes ->', out, '; lines:', txt.count('\n'))
