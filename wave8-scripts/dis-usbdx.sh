#!/bin/bash
# Wave8: UsbDeviceDxe entry point disassembly
awk '/^ +1000:/,/^ +1120:/' /tmp/wave8/devicedxe.dis | head -80
