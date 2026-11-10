import sys

cmd = ('serial=0 loader_return_after=300 small_cores_after=0 touchscreen=1 buttons=1 buttons_map=1 '
       'buttons_core=0xc400000 buttons_cnfg=0xc42d000 buttons_obs=0xc440000 '
       'cpus=8 bootcpu=7 soc_ipa_base=0x3e40000 soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 '
       'soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 modem_ipa_fw_at=0x8b910000 '
       'soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws')

v6 = ('serial=0 loader_return_after=60 cpus=8 bootcpu=7 soc_ipa_base=0x3e40000 '
      'soc_gsi_base=0x3e04000 soc_ipcc=0xed18000 soc_rsc=0x17a20000 soc_mpss_mem=0x8bc00000 '
      'modem_ipa_fw_at=0x8b910000 soc_ipa_stream=0x5c0 soc_ipa_stream_uc=0x5c2 soc_ipa_fw=ipa_fws')

assert len(v6) == 247, len(v6)          # the v6 payload's cmdline entry is 248 bytes with the NUL
assert all(part in cmd for part in v6.replace('loader_return_after=60', '').split()), 'every v6 argument carried over'
assert len(cmd) + 1 < 608 - 68, f'cmdline {len(cmd)} too long for the kernel line (608, loader adds ~68)'
open('/tmp/cmdline-v7.bin', 'wb').write(cmd.encode() + b'\0')
print('cmdline v7: %d bytes + NUL' % len(cmd))
print(cmd)
