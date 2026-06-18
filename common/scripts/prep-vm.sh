#!/bin/bash

set -e
set -x

SCRIPT_DIR="$(dirname $0)"
PREP_COMMON="${SCRIPT_DIR}/prep-common.sh"

# Set VM hostname from SMBIOS DMI tables injected by QEMU (-smbios type=1,product=...)
if [ -r /sys/class/dmi/id/product_name ]; then
    VM_NAME=$(cat /sys/class/dmi/id/product_name 2>/dev/null | tr -d '\n')
    if [[ -n "$VM_NAME" && "$VM_NAME" != "Standard PC"* && "$VM_NAME" != "Boachs"* ]]; then
        hostname "$VM_NAME" 2>/dev/null || true
        echo "$VM_NAME" > /etc/hostname 2>/dev/null || true
    fi
fi

# Remove root password completely for console login access
passwd -d root 2>/dev/null || true

# Configure SSH daemon to permit root login and password authentication
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null || true
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null || true

# If the modules directory is exposed through QEMU, mount it.
# The rest of the setup is the same as preping the host.
if grep -ac virt_kmods /sys/bus/virtio/drivers/9pnet_virtio/virtio*/mount_tag; then
  modules_dir="/lib/modules/$(uname -r)"
  mkdir -p $modules_dir
  mount -t 9p -o trans=virtio virt_kmods $modules_dir
fi

# Add /virt/common/scripts and /virt/common/bin to $PATH in ~/.bashrc
if ! grep -q "PATH=\"/virt/common/scripts:/virt/common/bin:\$PATH\"" ~/.bashrc; then
        echo >> ~/.bashrc
        echo "PATH=\"/virt/common/scripts:/virt/common/bin:\$PATH\"" >> ~/.bashrc
        echo >> ~/.bashrc
        source ~/.bashrc
fi

$PREP_COMMON

# Enslave primary hardware NIC to br_virt and copy its MAC address to the bridge interface.
# Enslaving strips IP reception from the NIC, so br_virt must inherit the deterministic QEMU MAC
# (52:54:...) to ensure vmaddr.py calculates the correct matching EUI-64 IPv6 address.
for dev in /sys/class/net/*/device; do
    if [ -e "$dev" ]; then
        iface=$(basename $(dirname "$dev"))
        mac=$(cat "/sys/class/net/$iface/address")
        ip link set dev "$iface" master br_virt
        ip addr flush dev "$iface"
        ip link set dev br_virt address "$mac"
        ip addr flush dev br_virt
        ip link set dev br_virt down
        ip link set dev br_virt up
        break
    fi
done
