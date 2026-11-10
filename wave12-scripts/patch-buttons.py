p = '/home/<host>/hakios/kernel/drivers/input/hakios.buttons.c'
s = open(p).read()

def rep(old, new, what):
    global s
    assert s.count(old) == 1, (what, s.count(old))
    s = s.replace(old, new, 1)
    print('buttons.c:', what, 'patched')

# 1. the boot-arg variables, after the arbiter register map's read helpers and before the peripheral table
old = '''static vm_offset_t arb_core, arb_cnfg, arb_observer;
'''
new = '''/*
 * The addresses above are the reference phone's (redwood, SM7325). On taro (SM8475, the OnePlus
 * Ace 2) the same arbiter sits elsewhere -- the live device tree has core at 0xc400000, cnfg at
 * 0xc42d000 and the observer at 0xc440000 -- so boot-args buttons_core=, buttons_cnfg= and
 * buttons_obs= (hexadecimal) move the three windows; the defaults leave this file as it was.
 */
static uint64_t arb_core_phys = ARB_CORE_PHYS, arb_cnfg_phys = ARB_CNFG_PHYS, arb_obs_phys = ARB_OBSERVER_PHYS;
'''
rep(old, new, '1 arbiter address variables')

# 2. the key roles: on taro the PON's RESIN_N is volume UP and GPIO6 of the PM8350 is volume DOWN
old = '''static struct button {
	const char *    name;
	uint32_t        record;         /* HAKIOS_BUTTON_* */
	bool            usable;         /* its input is what it was taken for */
	bool            live;           /* it has been seen released */
	bool            last;           /* the look before this one */
	bool            down;           /* as reported */
	uint64_t        since;          /* when it went down */
	uint32_t        presses;
} power = { .name = "power", .record = HAKIOS_BUTTON_LOCK },
    volume_up = { .name = "volume up", .record = HAKIOS_BUTTON_VOLUME_UP },
    volume_down = { .name = "volume down", .record = HAKIOS_BUTTON_VOLUME_DOWN };
'''
new = '''static struct button {
	const char *    name;
	uint32_t        record;         /* HAKIOS_BUTTON_* */
	bool            usable;         /* its input is what it was taken for */
	bool            live;           /* it has been seen released */
	bool            last;           /* the look before this one */
	bool            down;           /* as reported */
	uint64_t        since;          /* when it went down */
	uint32_t        presses;
} power = { .name = "power", .record = HAKIOS_BUTTON_LOCK },
    volume_up = { .name = "volume up", .record = HAKIOS_BUTTON_VOLUME_UP },
    volume_down = { .name = "volume down", .record = HAKIOS_BUTTON_VOLUME_DOWN };

/*
 * On the reference phone (redwood) the PON's RESIN_N is volume down and GPIO6 of the PM7325 is
 * volume up. The Ace 2 hangs them the other way round -- its tree gives RESIN_N the volume-up key
 * code (0x73) and GPIO6 of the PM8350 (slave 1, the same peripheral id 0x18d as the reference's
 * volume-up pin) the volume-down one -- so boot-arg buttons_map=1 swaps the two keys' names and
 * records; the reading of the two inputs is the same code either way.
 */
static void
keys_map(uint32_t map)
{
	if (map != 1) {
		return;
	}
	volume_up.name = "volume down";
	volume_up.record = HAKIOS_BUTTON_VOLUME_DOWN;
	volume_down.name = "volume up";
	volume_down.record = HAKIOS_BUTTON_VOLUME_UP;
}
'''
rep(old, new, '2 key roles')

# 3. the thread: read the boot args, then map the addresses with them
old = '''	printf("buttons: step 1: map the PMIC arbiter (%#lx, %#lx, %#lx) and read its version\\n", ARB_CORE_PHYS, ARB_CNFG_PHYS,
	    ARB_OBSERVER_PHYS);
	arb_core = ml_io_map(ARB_CORE_PHYS, ARB_CORE_SIZE);
	arb_cnfg = ml_io_map(ARB_CNFG_PHYS, ARB_CNFG_SIZE);
	arb_observer = ml_io_map(ARB_OBSERVER_PHYS, ARB_OBSERVER_SIZE);
'''
new = '''	{
		uint32_t map = 0;

		PE_parse_boot_argn("buttons_core", &arb_core_phys, sizeof(arb_core_phys));
		PE_parse_boot_argn("buttons_cnfg", &arb_cnfg_phys, sizeof(arb_cnfg_phys));
		PE_parse_boot_argn("buttons_obs", &arb_obs_phys, sizeof(arb_obs_phys));
		PE_parse_boot_argn("buttons_map", &map, sizeof(map));
		keys_map(map);
	}
	printf("buttons: step 1: map the PMIC arbiter (%#llx, %#llx, %#llx) and read its version\\n", arb_core_phys,
	    arb_cnfg_phys, arb_obs_phys);
	arb_core = ml_io_map((vm_offset_t)arb_core_phys, ARB_CORE_SIZE);
	arb_cnfg = ml_io_map((vm_offset_t)arb_cnfg_phys, ARB_CNFG_SIZE);
	arb_observer = ml_io_map((vm_offset_t)arb_obs_phys, ARB_OBSERVER_SIZE);
'''
rep(old, new, '3 thread boot args')

open(p, 'w').write(s)
print('buttons.c written')
