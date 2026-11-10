/*
 * Wave 11 resident launchd stub (HakiOS on PHK110, boot_b v6 ramdisk).
 *
 * Wave 10 (Boot #12) reached v0.1: this slot of process 1 was the hello
 * program, which printed its signs of life and then exited -- and an exiting
 * process 1 panics the kernel ("initproc failed to start"), which ended the
 * run after a few seconds, before the slow cores (cpu 4-6, phys 0x300/0x200/
 * 0x100) had been woken at all.
 *
 * This stub is hello with the exit left out: the same raw-syscall static
 * arm64 Mach-O (no libc, no dyld; the kernel's mockfs presents the ramdisk,
 * which is this very file, as /sbin/launchd), but once it has printed its
 * signs of life it stays in an infinite sleep loop -- a heartbeat once every
 * ten seconds and the thermal lines once every five -- so the kernel lives
 * on for the whole loader_return_after=60 window and all eight cores can
 * come up. No MMIO is touched: only /dev/console writes, sysctl reads and
 * select() sleeps, exactly the calls hello proved on this machine.
 *
 * Built with the same toolchain as hello (userland/build.sh line 24):
 *   xnu-clang -arch arm64 -Os -static -nostdlib -ffreestanding
 *             -fno-stack-protector -fno-builtin -Wall -Wextra
 *             -Wl,-e,_start -Wl,-pagezero_size,0x100000000
 */
typedef unsigned long u64;

/* XNU arm64 system call: number in x16, arguments in x0.., "svc #0x80"; carry set on error */
static long
syscall3(long num, long a, long b, long c)
{
	register long x16 __asm__("x16") = num;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	__asm__ volatile ("svc #0x80" : "+r" (x0) : "r" (x16), "r" (x1), "r" (x2) : "memory", "cc");
	return x0;
}

/* the same with six arguments, for sysctlbyname(name, namelen, old, &oldlen, new, newlen) */
static long
syscall6(long num, long a, long b, long c, long d, long e, long f)
{
	register long x16 __asm__("x16") = num;
	register long x0 __asm__("x0") = a;
	register long x1 __asm__("x1") = b;
	register long x2 __asm__("x2") = c;
	register long x3 __asm__("x3") = d;
	register long x4 __asm__("x4") = e;
	register long x5 __asm__("x5") = f;
	__asm__ volatile ("svc #0x80" : "+r" (x0) : "r" (x16), "r" (x1), "r" (x2), "r" (x3), "r" (x4), "r" (x5) : "memory", "cc");
	return x0;
}

#define SYS_write   4
#define SYS_open    5
#define SYS_getpid  20
#define SYS_getuid  24
#define SYS_select  93
#define SYS_sysctlbyname 274
#define O_RDWR      2

static unsigned
length(const char *s)
{
	unsigned n = 0;
	while (s[n]) {
		n++;
	}
	return n;
}

static void
put(int fd, const char *s)
{
	syscall3(SYS_write, fd, (long)s, length(s));
}

static void
put_number(int fd, long v)
{
	char buf[24];
	int i = sizeof(buf);
	buf[--i] = 0;
	do {
		buf[--i] = (char)('0' + v % 10);
		v /= 10;
	} while (v);
	put(fd, buf + i);
}

/* "name=value" for a string sysctl, or nothing at all if the kernel has no such name */
static void
show_string(int fd, const char *name)
{
	char value[1100];
	u64 size = sizeof(value);

	if (syscall6(SYS_sysctlbyname, (long)name, length(name), (long)value, (long)&size, 0, 0) == 0) {
		put(fd, name);
		put(fd, "=");
		put(fd, value);
		put(fd, "\n");
	}
}

/* ... for an int sysctl (four bytes) */
static void
show_int(int fd, const char *name)
{
	int value = 0;
	u64 size = sizeof(value);

	if (syscall6(SYS_sysctlbyname, (long)name, length(name), (long)&value, (long)&size, 0, 0) == 0) {
		put(fd, name);
		put(fd, "=");
		if (value < 0) {
			put(fd, "-");
			value = -value;
		}
		put_number(fd, value);
		put(fd, "\n");
	}
}

void
start(void)
{
	int fd = (int)syscall3(SYS_open, (long)"/dev/console", O_RDWR, 0);

	put(fd, "\nHello from user space on Darwin!\n");
	put(fd, "I am process ");
	put_number(fd, syscall3(SYS_getpid, 0, 0, 0));
	put(fd, ", uid ");
	put_number(fd, syscall3(SYS_getuid, 0, 0, 0));
	put(fd, ", console fd ");
	put_number(fd, fd);
	put(fd, ".\n");

	{
		char version[96];
		u64 size = sizeof(version);
		long failed = syscall6(SYS_sysctlbyname, (long)"kern.hakios.version", 19, (long)version, (long)&size, 0, 0);

		put(fd, "kernel.ver=");
		put(fd, failed ? "(sysctl kern.hakios.version not available)" : version);
		put(fd, "\n");
	}

	show_string(fd, "kern.hakios.soc_name");
	show_int(fd, "kern.hakios.soc_id");
	show_int(fd, "kern.hakios.pmic_peripherals");
	show_string(fd, "kern.hakios.thermal_sensors");

	/*
	 * The wave 11 change: process 1 does not exit. Heartbeat once every ten
	 * seconds, thermal lines once every five, forever -- the loader's
	 * loader_return_after timer ends the run at 60 s, not this process.
	 */
	put(fd, "launchd stub resident (wave11): not exiting, sleeping forever\n");
	for (long second = 0;; second++) {
		long tv[2] = { 1, 0 };

		syscall6(SYS_select, 0, 0, 0, 0, (long)tv, 0);
		if (second % 5 == 4) {
			show_int(fd, "kern.hakios.thermal_max_mc");
			show_string(fd, "kern.hakios.thermal_hottest");
		}
		if (second % 10 == 9) {
			put(fd, "launchd stub alive: t=");
			put_number(fd, second + 1);
			put(fd, "s\n");
		}
	}
}
