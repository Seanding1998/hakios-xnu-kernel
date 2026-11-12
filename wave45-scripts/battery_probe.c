/*
 * battery_probe: the wave45 gate-D judge, follow-up edition. The carrier's
 * PATH has no /usr/sbin/sysctl (the discovery round's `command not found`),
 * so the kern.hakios.battery_* values are read here through sysctlbyname(),
 * the same kernel interface the missing tool would have used -- the oids are
 * the wave43 driver's registrations (drivers/power/hakios.battery.c, the
 * SYSCTL_INT block under kern.hakios).
 *
 * One run = one snapshot. The runner runs it twice spaced a few seconds for
 * the series. Every value is printed with its read result so a refused oid is
 * recorded, never guessed.
 *
 * Build (the fence_probe recipe):
 *   xnu-clang -arch arm64 -isysroot $HOME/theos/sdks/iPhoneOS16.5.sdk -O1 \
 *     -framework CoreFoundation -framework IOKit -o battery_probe battery_probe.c
 */
#include <sys/sysctl.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>

static const char *OIDS[] = {
	"kern.hakios.battery_soc",
	"kern.hakios.battery_voltage_mv",
	"kern.hakios.battery_current_ma",
	"kern.hakios.battery_temperature_c",
	"kern.hakios.battery_present",
	"kern.hakios.battery_charger_present",
	"kern.hakios.battery_charging",
	"kern.hakios.battery_soc_estimated",
	"kern.hakios.battery_charger_action",
	"kern.hakios.battery_full_uah",
};

int
main(void)
{
	unsigned ok = 0;

	for (unsigned i = 0; i < sizeof(OIDS) / sizeof(OIDS[0]); i++) {
		int value = 0;
		size_t len = sizeof(value);

		if (sysctlbyname(OIDS[i], &value, &len, NULL, 0) == 0) {
			ok++;
			printf("BATTERY_PROBE: %s = %d\n", OIDS[i], value);
		} else {
			printf("BATTERY_PROBE: %s = <unreadable, errno %d>\n", OIDS[i], errno);
		}
	}
	printf("BATTERY_PROBE: readable %u of %zu oids\n", ok, sizeof(OIDS) / sizeof(OIDS[0]));
	return ok == sizeof(OIDS) / sizeof(OIDS[0]) ? 0 : 1;
}
