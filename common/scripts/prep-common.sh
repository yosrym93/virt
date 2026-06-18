#!/bin/sh

set -e
set -x

if grep -iq intel /proc/cpuinfo; then
  mod=kvm_intel
elif grep -iq amd /proc/cpuinfo; then
  mod=kvm_amd
else
  echo "Cannot find KVM vendor module"
  exit 1
fi

modprobe kvm 2>/dev/null || true

if lsmod | grep -wq $mod; then
	# If the vendor module is loaded without nested=1, reload it with it.
	if grep -q 0 /sys/module/$mod/parameters/nested 2>/dev/null; then
		rmmod $mod 2>/dev/null || true
		modprobe $mod nested=1 2>/dev/null || true
	fi
else
	# If the vendor module is not loaded at all, load it with nested=1.
	modprobe $mod nested=1 2>/dev/null || true
fi
