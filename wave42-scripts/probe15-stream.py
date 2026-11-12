#!/usr/bin/env python3
"""Wave 42: dissect the sha-rt returned stream (w42ssh8). Is the extra data a PTY
echo (blob subsequence), console noise, or byte mangling?"""
import hashlib
import re

blob = None
# reconstruct the blob is impossible (random); instead analyze structure
data = open('wave42-scripts/tssh42-w42ssh8-sha-rt-03.out', 'rb').read()
print("stream bytes:", len(data))
i = data.find(b'\n')
j = data.find(b'\n', i + 1)
print("line1 (hash):", data[:i][:80])
print("line2 (count):", data[i + 1:j][:40])
payload = data[j + 1:]
print("payload bytes after 2 lines:", len(payload))

# how many times does the sha-line pattern appear? (echo would repeat it)
hashline = data[:i]
occurrences = [m.start() for m in re.finditer(re.escape(data[:j]), data)]
print("header (2 lines) occurrences in stream:", len(occurrences), occurrences[:5])

# printable ratio
printable = sum(1 for b in payload if 32 <= b < 127 or b in (9, 10, 13))
print(f"payload printable ratio: {printable / max(1, len(payload)):.2%}")
print("payload head 64:", payload[:64])
print("payload tail 64:", payload[-64:])

# look for long ascending runs / repeated blocks (echo signatures)
step = len(payload) // 8
for k in range(0, 8):
    seg = payload[k * step:(k + 1) * step]
    print(f"  seg{k} sha256 {hashlib.sha256(seg).hexdigest()[:12]} head={seg[:12]!r}")
