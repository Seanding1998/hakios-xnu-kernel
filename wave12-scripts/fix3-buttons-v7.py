p = '/home/<host>/hakios/kernel/drivers/input/hakios.buttons.c'
s = open(p).read()

def rep(old, new, what):
    global s
    assert s.count(old) == 1, (what, s.count(old))
    s = s.replace(old, new, 1)
    print(what, 'patched')

# 1. version gate: the Ace 2's arbiter answers 0x70000000 (Boot #14 evidence). Version 7 keeps the
#    channel command/status/data layout but moves the APID->PPID table, the owner table and the
#    observer stride, and counts its channels differently (Linux drivers/spmi/spmi-pmic-arb.c v7 ops).
rep('''#define ARB_VERSION             0x000
#define ARB_VERSION_5           0x50000000u     /* what follows is version 5's; 7 moved things again */
#define ARB_VERSION_7           0x70000000u
#define ARB_FEATURES            0x004           /* [10:0] the number of channels */
#define ARB_CHANNEL(n)          (0x900 + 4 * (n))       /* core: [19:8] slave and peripheral, [24] interrupts go to the owner */
#define ARB_CHANNEL_INTERRUPTS  (1u << 24)
#define ARB_OWNER(n)            (0x700 + 4 * (n))       /* cnfg: [2:0] the system that may write through channel n */
#define ARB_MAX_CHANNELS        512
''',
'''#define ARB_VERSION             0x000
#define ARB_VERSION_5           0x50000000u
#define ARB_VERSION_7           0x70000000u
#define ARB_VERSION_8           0x80000000u
#define ARB_FEATURES            0x004           /* [10:0] the number of channels (v5 and v7 read it the same way) */
#define ARB_CHANNEL(n)          (arb_apid_map + 4 * (n)) /* core: [19:8] slave and peripheral, [24] interrupts go to the owner; v5 keeps the table at 0x900, v7 at 0x2000 */
#define ARB_CHANNEL_INTERRUPTS  (1u << 24)
#define ARB_OWNER(n)            (arb_owner_base + 4 * (n)) /* cnfg: [2:0] the system that may write through channel n; v5 keeps the table at 0x700, v7 at 0 */
#define ARB_MAX_CHANNELS        1024            /* v7 answers 768 here (Boot #14: "768 channels") */

/* where the arbiter keeps its tables, and how wide its observer channels are spaced: version 5's, the reference phone's */
static uint32_t arb_apid_map = 0x900, arb_owner_base = 0x700;
static uint32_t arb_obs_system = 0x10000, arb_obs_stride = 0x80;
''', '1 version gate constants')

# 2. the observer channel base: v5 puts 0x10000 per system and 0x80 per channel, v7 0x8000 and 0x20
rep('''	vm_offset_t channel = arb_observer + 0x10000UL * ARB_SYSTEM + 0x80UL * p->channel;''',
'''	vm_offset_t channel = arb_observer + (uint32_t)arb_obs_system * ARB_SYSTEM +
	    (uint32_t)arb_obs_stride * p->channel;''',
    '2 observer channel base')

# 3. the core window must be big enough for v7's table at 0x2000 (the tree gives the core 0x3000)
rep('''#define ARB_CORE_SIZE           0x1100UL''',
'''#define ARB_CORE_SIZE           0x3000UL        /* v5 needs 0x1100; v7 keeps its APID->PPID table at 0x2000 */''',
    '3 core window size')

# 4. pick the table places by the version the arbiter answers with
rep('''	if (version < ARB_VERSION_5 || version >= ARB_VERSION_7) {
		printf("buttons: this driver knows version 5 of the arbiter only: no buttons\\n");
		goto out;
	}
	if (channels == 0 || channels > ARB_MAX_CHANNELS) {
		channels = ARB_MAX_CHANNELS;
	}''',
'''	if (version < ARB_VERSION_5 || version >= ARB_VERSION_8) {
		printf("buttons: this driver knows versions 5 and 7 of the arbiter only: no buttons\\n");
		goto out;
	}
	if (version >= ARB_VERSION_7) {
		/* version 7 (the Ace 2's): the tables moved (Linux spmi-pmic-arb.c's v7 ops) */
		arb_apid_map = 0x2000;
		arb_owner_base = 0;
		arb_obs_system = 0x8000;
		arb_obs_stride = 0x20;
		printf("buttons: version 7: APID->PPID table at core+0x2000, owner table at cnfg+0, "
		    "observer channels at obsrvr+0x8000*system+0x20*apid\\n");
	}
	if (channels == 0 || channels > ARB_MAX_CHANNELS) {
		channels = ARB_MAX_CHANNELS;
	}''', '4 version-dependent tables')

open(p, 'w').write(s)
