p = '/home/<host>/hakios/kernel/devices/phk110/drivers/input/hakios.s3910.c'
s = open(p).read()

def rep(old, new, what):
    global s
    assert s.count(old) == 1, (what, s.count(old))
    s = s.replace(old, new, 1)
    print(what, 'patched')

# Boot #15: data abort reading gcc+0x62008 (the sm8450 APCS vote register) -- the mapping was
# 0x60000, the tree gives the gcc 0x1f4200 bytes and the vote register sits at 0x62008.
rep('''#define GCC_SIZE                0x60000UL''',
'''#define GCC_SIZE                0x1f4200UL      /* the tree's own size; sm8450's vote register is at 0x62008 */''',
    's3910.c GCC_SIZE')

open(p, 'w').write(s)
