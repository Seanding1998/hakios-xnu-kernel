#!/bin/bash
# Wave8: UsbConfigDxe entry point (0x1000..) and GUID xref scan
sed -n '60,140p' /tmp/wave8/configdxe.patched.dis
