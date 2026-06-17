#!/bin/sh

set -e
set -x

if ! ip link show tap0 >/dev/null 2>&1; then
	ip tuntap add dev tap0 mode tap
fi

if ! ip link show tap0 | grep UP; then
	ip link set dev tap0 up
fi

if grep -iq intel /proc/cpuinfo; then
  mod=kvm_intel
elif grep -iq amd /proc/cpuinfo; then
  mod=kvm_amd
else
  echo "Cannot find KVM vendor module"
  exit 1
fi

modprobe kvm

if lsmod | grep -wq $mod; then
	# If the vendor module is loaded without nested=1, reload it with it.
	if grep 0 /sys/module/$mod/parameters/nested; then
		rmmod $mod
		modprobe $mod nested=1
	fi
else
	# If the vendor module is not loaded at all, load it with nested=1.
	modprobe $mod nested=1
fi
