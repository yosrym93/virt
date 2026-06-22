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

# Create software bridge switch if it does not exist (avoids RTNETLINK File exists error)
if ! ip link show dev br_virt >/dev/null 2>&1; then
	ip link add br_virt type bridge
fi
ip link set br_virt up

COMMON_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_BIN="/usr/local/bin"

# Symlink all common tools into /usr/local/bin for global non-interactive access
mkdir -p "${TARGET_BIN}"
for sub in scripts aliases bin qemu; do
    dir="${COMMON_DIR}/${sub}"
    if [ -d "$dir" ]; then
        for item in "${dir}"/*; do
            if [ -f "$item" ]; then
                chmod +x "$item" 2>/dev/null || true
                ln -sf "$item" "${TARGET_BIN}/$(basename "$item")"
            fi
        done
    fi
done

# Symlink QEMU bios files to a path that is checked by QEMU by default.
# This is needed for invocations to QEMU through scripts (e.g. kvm-unit-tests)
# that do not allow specifying a path to the bios files.
mkdir -p "${COMMON_DIR}/share"
ln -sf ../qemu/pc-bios "${COMMON_DIR}/share/qemu"
