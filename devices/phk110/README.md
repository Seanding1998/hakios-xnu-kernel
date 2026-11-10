# OnePlus Ace 2 (`PHK110`)

An SM8475 ("cape") port of HakiOS, brought up from the upstream `redwood`
(SM7325) reference device. Everything below was verified on this phone; the
full log trail lives in [`docs/phk110/STATUS.md`](../../docs/phk110/STATUS.md)
and [`docs/phk110/waves/`](../../docs/phk110/waves/) ("Boot #N" numbers refer
to that timeline).

| | |
|---|---|
| Vendor | OnePlus |
| SoC | `SM8475` (Snapdragon 8+ Gen 1, "cape"), 16 GB RAM |
| Configuration | loader cmdline built from `soc.args` + the boot-args in `device.conf` |
| Maintainer | the PHK110 port team (this branch) |
| Base | [hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel) (redwood reference) |
| UEFI | takasugl's udonPkg rebuilt for this board (`FD_BASE=0xA7100000`, `PAYLOAD_BASE=0xF4000000`) |
| Boot path | the `boot_b` slot only; the daily Android `boot_a` slot is never touched |

## What works

| Part | State | |
|---|---|---|
| display | works | the panel through UEFI's framebuffer at 1240x2772; the kernel fb console scrolls, and a screen-recording boot-arg path exists (rec_secs/rec_ring) |
| buttons | works | power and both volume keys, read over the PMIC's SPMI bus (arbiter protocol v7 — the upstream driver only knew v5); press/release events with ms timestamps (Boot #16) |
| cpu | works | all 8 cores up; with `small_cores_after=0` the 7 application cores come online within an 8 ms window (big cores 1-3, little cores 4-6) |
| touch | probe works | Synaptics S3910, TouchComm v1 protocol over a GENI SPI port: `part number "S3910PA0B0-15.2"`, 1240x2772 panel, report config read, `touch screen ready` (~1.0 s probe, Boot #21). The read direction is bit-banged because the port's firmware keeps the GENI FIFO interface disabled, and the controller hands out one 9-byte block per chip-select frame, re-arming on a ~20 ms cadence |
| storage | works | UFS: 129 partitions exposed read-only (`ufs=2`), the `ufs_darwin_data` volume writable (`ufs_write=1 var_hfs=...`), `/private/var` kept across boots with journal replay verified both ways (Boot #22-#24) |
| userland | works | real Apple launchd as pid 1: `hardware target : d22ap` accepted, 28 processes (SpringBoard, backboardd), Procursus prefix grafted at `/var/jb` (Boot #25) |
| ssh | works | three independent SSH sessions over the loader's USB network (`en0`, 10.0.0.2/30), root shell, a 256 KiB verified transfer, clean FIN/ACK exit and the loader still alive afterwards (2026-11-10) |
| usb serving | works | the loader's USB command server (getvar / oem log / oem upload, a 216 KB upload verified for length and content). Getting here required identifying a defect in the vendor USB stack's reset flow: a CORESOFTRESET timeout leaves the core half-reset for every subsequent boot (fixed in stage 24, 2026-11-09) |
| session limit | partly | the 1800 s session cap is verified end to end; longer sessions hit a pre-existing `panic: vnode table is full` |
| gpu | no | WindowServer/CoreAnimation not yet up — planned for v0.5, same as upstream's roadmap |
| wifi | tooling | the WCN6750/ath11k checkers and packager are ready (`wave30-scripts/`); nothing on the air yet |
| cellular / audio / battery / haptic / camera | no | not attempted yet |

## Safety boundary

The port boots through the `boot_b` slot: flashing and booting it never writes
the daily Android `boot_a` slot. A failed or crashing session falls back to
Android through the bootloader's own A/B fallback; getting back by hand is
`fastboot set_active a` + reboot. A 20 GB `darwin` volume was carved at the
tail of userdata, with the data volume's header and signature verified healthy
before and after (stage 16b/16c).
