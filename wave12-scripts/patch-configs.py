def rep(path, old, new, what):
    s = open(path).read()
    assert s.count(old) == 1, (what, s.count(old))
    open(path, 'w').write(s.replace(old, new, 1))
    print(what, 'patched')

# 1. phk110.config: the S3910 driver on
p = '/home/<host>/hakios/kernel/devices/phk110/configs/phk110.config'
rep(p,
    '# CONFIG_HAKIOS_GOODIX is not set\n# CONFIG_HAKIOS_BUTTONS is not set\n',
    '# the touch screen, this phone own driver of the device repository (devices/phk110/drivers/input/)\nCONFIG_HAKIOS_S3910=y\n# CONFIG_HAKIOS_GOODIX is not set\n# CONFIG_HAKIOS_BUTTONS is not set\n',
    'phk110.config S3910 on')

# 2. common_defconfig: name it (the reference phone does not use it)
p = '/home/<host>/hakios/kernel/configs/common_defconfig'
rep(p,
    'CONFIG_HAKIOS_GOODIX=y\n',
    'CONFIG_HAKIOS_GOODIX=y\n\n# the OnePlus Ace 2 touch controller, a driver of that device repository: not this phone\n# CONFIG_HAKIOS_S3910 is not set\n',
    'common_defconfig S3910 off')

# 3. qemu_defconfig: name it
p = '/home/<host>/hakios/kernel/devices/qemu/configs/qemu_defconfig'
rep(p,
    '# CONFIG_HAKIOS_GOODIX is not set\n',
    '# CONFIG_HAKIOS_GOODIX is not set\n# CONFIG_HAKIOS_S3910 is not set\n',
    'qemu_defconfig S3910 off')
