#!/bin/bash
set -e

trap 'echo -e "\n\033[1;31m========================================\nCRITICAL: virt-init.service FAILED!\nRun: journalctl -u virt-init.service -b\n========================================\033[0m\n" > /dev/console 2>/dev/null || true' ERR

echo "9p mount tags:"
for t in /sys/bus/virtio/drivers/9pnet_virtio/virtio*/mount_tag; do
	cat $t
done

mkdir -p /virt

# Mount shared root directory read-only
mount -t 9p -o trans=virtio virt_root /virt

if [ ! -x /virt/common/scripts/prep-vm.sh ]; then
    echo "ERROR: /virt/common/scripts/prep-vm.sh is missing or not executable!" >&2
    exit 1
fi

/virt/common/scripts/prep-vm.sh
