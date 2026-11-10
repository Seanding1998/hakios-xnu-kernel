def rep(path, old, new, what):
    s = open(path).read()
    assert s.count(old) == 1, (what, s.count(old))
    open(path, 'w').write(s.replace(old, new, 1))
    print(what, 'patched')

p = '/home/<host>/hakios/kernel/devices/phk110/configs/phk110.config'
rep(p, '# CONFIG_HAKIOS_BUTTONS is not set\n',
    '# the power and volume keys: the reference driver (hakios.buttons.c) reading this phone arbiter\n# (buttons_core=/buttons_cnfg=/buttons_obs=) and its key order (buttons_map=1)\nCONFIG_HAKIOS_BUTTONS=y\n',
    'phk110.config BUTTONS on')
