#!/bin/sh
set -e

# Bring up QEMU tap interface
ip link set dev "$1" up

# If virtual switch exists, enslave tap interface to it for inter-VM SSH
if ip link show dev br_virt >/dev/null 2>&1; then
    ip link set dev "$1" master br_virt
fi
