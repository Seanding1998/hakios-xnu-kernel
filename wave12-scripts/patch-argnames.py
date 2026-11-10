def rep(path, old, new, what):
    s = open(path).read()
    assert s.count(old) == 1, (what, s.count(old))
    open(path, 'w').write(s.replace(old, new, 1))
    print(what, 'patched')

# the four new buttons_* boot arguments get their CONFIG_ names everywhere the existing ones are named
new_names = (
    '# CONFIG_BUTTONS_CNFG is not set\n'
    '# CONFIG_BUTTONS_CORE is not set\n'
    '# CONFIG_BUTTONS_MAP is not set\n'
    '# CONFIG_BUTTONS_OBS is not set\n'
)

p = '/home/<host>/hakios/kernel/configs/common_defconfig'
rep(p, '# CONFIG_BUTTONS_STEPS is not set\n',
    '# CONFIG_BUTTONS_STEPS is not set\n' + new_names,
    'common_defconfig new arg names')

p = '/home/<host>/hakios/kernel/devices/phk110/configs/phk110.config'
rep(p, '# CONFIG_HAKIOS_BUTTONS is not set\n',
    '# CONFIG_HAKIOS_BUTTONS is not set\n' + new_names,
    'phk110.config new arg names')
