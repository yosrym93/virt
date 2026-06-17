#!/bin/bash

set -e
set -x

SCRIPT_DIR="$(dirname $0)"
PREP_COMMON="${SCRIPT_DIR}/prep-common.sh"

# If the modules directory is exposed through QEMU, mount it.
# The rest of the setup is the same as preping the host.
if grep -ac kmodules /sys/bus/virtio/drivers/9pnet_virtio/virtio*/mount_tag; then
  modules_dir="/lib/modules/$(uname -r)"
  mkdir -p $modules_dir
  mount -t 9p -o trans=virtio kmodules $modules_dir
fi

# Add /virt/common/scripts and /virt/common/bin to $PATH in ~/.bashrc
if ! grep -q "PATH=\"/virt/common/scripts:/virt/common/bin:\$PATH\"" ~/.bashrc; then
        echo >> ~/.bashrc
        echo "PATH=\"/virt/common/scripts:/virt/common/bin:\$PATH\"" >> ~/.bashrc
        echo >> ~/.bashrc
        source ~/.bashrc
fi

$PREP_COMMON
