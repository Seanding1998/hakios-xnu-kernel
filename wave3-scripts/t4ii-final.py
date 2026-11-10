import struct, sys, gzip
data = open('/home/<host>/hakios/kernel/xnu-phk110.img', 'rb').read()
page = struct.unpack_from('<I', data, 36)[0]
kern = data[page:]
blob = gzip.decompress(kern[:kern.find(b'\xd0\x0d\xfe\xed') - 0])
shim = blob[:176]
open('/tmp/shim-in-img.bin','wb').write(shim)
# raw check: MOVZ X5, #0xC000, LSL#16 => 0xD2B80005 ; bytes LE 05 80 b8 d2
print('shim words:', [f'{w:08x}' for w in struct.unpack_from('<44I', shim, 0)])
print('expect movz x5,#0xc000,lsl#16 = d2b80005 (LE bytes 05 80 b8 d2)')
print('found:', any(w == 0xd2b80005 for w in struct.unpack('<44I', shim)))
