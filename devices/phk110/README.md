# OnePlus Ace 2 (`PHK110`)

An SM8475 ("cape") port of HakiOS, brought up from the upstream `redwood`
(SM7325) reference device. State below is what has actually been seen on this
phone (Boots #1-#39); the full log trail is in
[`docs/phk110/STATUS.md`](../../docs/phk110/STATUS.md) and
[`docs/phk110/waves/`](../../docs/phk110/waves/).

| | |
|---|---|
| Vendor | OnePlus |
| SoC | `SM8475` (Snapdragon 8+ Gen 1, "cape"), 16 GB RAM |
| Configuration | loader cmdline built from `soc.args` + the boot-args in `device.conf` |
| Maintainer | the PHK110 port team (this branch) |
| Base | [hakios-xnu-kernel](https://github.com/oosexgang/hakios-xnu-kernel) (redwood reference) |
| UEFI | takasugl's udonPkg rebuilt for this board (`FD_BASE=0xA7100000`, `PAYLOAD_BASE=0xF4000000`) |
| Boot path | `boot_b` slot only, RAM-level; the Android `boot_a` slot is never touched |

## What works

| Part | State | |
|---|---|---|
| display | works | the panel through UEFI's framebuffer at 1240x2772; the kernel fb console scrolls, and a screen-recording boot-arg path exists (rec_secs/rec_ring) |
| buttons | works | power and both volume keys through the PMIC SPMI **v7** arbiter (upstream driver only knew v5); real press/release events with ms timestamps (Boot #16) |
| cpu | works | all 8 cores up (7 AP cores online within an 8 ms window with `small_cores_after=0`; big cores at 1-3, slow 4-6) |
| touch | probe works | Synaptics S3910 TouchComm **v1** over GENI SPI: `part number "S3910PA0B0-15.2"`, 1240x2772 panel, report config read, `touch screen ready` (~1.0 s probe, Boot #21); needs a bitbang read path because the SE firmware keeps the GENI FIFO interface off, and 9-byte blocks re-armed on a ~20 ms cadence |
| storage | works | UFS: 129 partitions exposed read-only (`ufs=2`), write path to `ufs_darwin_data` (`ufs_write=1 var_hfs=...`), `/private/var` kept between boots with cross-boot journal replay (Boot #22-#24) |
| userland | works | real Apple launchd takes pid 1: `hardware target : d22ap` accepted, 28 processes (SpringBoard, backboardd), Procursus `/var/jb` prefix grafted (Boot #25) |
| ssh | works | `WAVE21-SSH-OK` verdict: 3 independent SSH sessions over the loader's USB network (`en0`, 10.0.0.2/30), root shell, a 256 KiB verified transfer, clean FIN/ACK exit and the loader still alive after (2026-11-10) |
| usb serving | works | loader USB command server (getvar / oem log / oem upload, 216 KB verified) — required fixing the vendor reset flow: CORESOFTRESET-timeout leaves a half-reset core (the "H4" root cause, Wave 24) |
| session limit | partly | 1800 s cap verified end to end; longer sessions hit `panic: vnode table is full` (pre-existing, F6) |
| gpu | no | WindowServer/CoreAnimation not yet up — planned v0.5 boundary, same as upstream's roadmap step |
| wifi | tooling | WCN6750/ath11k tooling prepared (Wave 30); nothing on the air yet |
| cellular / audio / battery / haptic / camera | no | not attempted yet |

## Safety boundary

The port boots through the `boot_b` slot: flashing and booting it never writes
the daily Android `boot_a` slot. A failed or crashing session falls back to
Android through the bootloader's own A/B fallback; getting back to Android by
hand is `fastboot set_active a` + reboot. The 200 GB userdata volume is
repartitioned-adjacent only in that a 20 GB `darwin` volume was carved
at the tail with the data volume verified healthy afterwards (Wave 16b P0).
