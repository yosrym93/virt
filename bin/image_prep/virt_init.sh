#!/bin/bash
set -e

mkdir -p /virt
echo "Available 9p virtio mount tags:"
grep -H . /sys/bus/virtio/drivers/9pnet_virtio/virtio*/mount_tag 2>/dev/null || echo "None found"

# Mount shared root directory read-only
mount -t 9p -o trans=virtio virt_root /virt

mkdir -p /virt/common/imgs
# Mount working image overlays read-write
mount -t 9p -o trans=virtio virt_imgs /virt/common/imgs

if [ -x /virt/common/scripts/prep-vm.sh ]; then
    /virt/common/scripts/prep-vm.sh
fi
