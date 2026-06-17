#!/bin/bash

set -e
set -x

SCRIPT_DIR="$(dirname $0)"
PREP_COMMON="${SCRIPT_DIR}/prep-common.sh"

# Remove root password completely for console login access
passwd -d root 2>/dev/null || true

# Configure SSH daemon to permit root login and password authentication
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null || true
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null || true

# Re-enable console line wrapping (DECAWM) and window sizing on interactive shells
if [ -f /etc/profile ]; then
    if ! grep -q 'printf "\\033\[?7h"' /etc/profile; then
        echo 'printf "\033[?7h" 2>/dev/null || true' >> /etc/profile
        echo 'shopt -s checkwinsize 2>/dev/null || true' >> /etc/profile
    fi
fi

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
