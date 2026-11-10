p = '/home/<host>/hakios/kernel/devices/phk110/drivers/input/hakios.s3910.c'
s = open(p).read()

def rep(old, new, what):
    global s
    assert s.count(old) == 1, (what, s.count(old))
    s = s.replace(old, new, 1)
    print(what, 'patched')

# Boot #14: data abort at rail_on+0x294 -- rpmh_wait applies TCS() to the address that
# the caller had already expanded: rpmh_wait(TCS(TCS_IRQ_STATUS), ...) read
# *(rsc + 0xd00 + (rsc + 0xd04)). Pass the register offset itself.
rep('\tdone = rpmh_wait(TCS(TCS_IRQ_STATUS), 1, 1, "the request");\n',
    '\tdone = rpmh_wait(TCS_IRQ_STATUS, 1, 1, "the request");   /* rpmh_wait applies TCS itself */\n',
    's3910.c rpmh_wait double-TCS fix')

open(p, 'w').write(s)
