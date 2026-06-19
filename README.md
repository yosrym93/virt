# Virt: QEMU/KVM Virtualization & Testing Utilities

`virt` is a set of scripts and helpers for managing QEMU/KVM virtual machines and optionally syncing with a remote test host.

## Overview

- `prep_base_image.py`: Prepares stock Linux cloud images by converting them to `.qcow2`, injecting SSH keys, and setting up serial console autologin.
- `vm.py`: CLI for managing VM lifecycle (`run`, `ssh`, `scp`, `kill`).
- `dsync.py`: Syncs local VM management scripts (and optionally compiled kernel binaries) to a remote test machines.

## Naming & Networking

- **Nested VMs Auto-Naming Scheme**: VMs auto-qualify their names based on their parent hierarchy. Running `vmr test` on the host spawns VM `test`. Running `vmr nested` inside VM `test` spawns child VM `test-nested`.
- **Universal Inter-VM Networking**: All VMs attached to the local bridge can connect directly to each other via SSH.

## Setup & Repository Map

- `common/`: Shared runtime payload mirrored across development workstations, test hosts, and guest VMs.
  - `common/scripts/`: Core orchestration tools (`vm.py`, `dsync.py`, `prep-host.sh`, `prep-vm.sh`, `ifup.sh`, `vmaddr.py`).
  - `common/aliases/`: Shorthand CLI wrappers linked into `/usr/local/bin` (`vmr`, `vms`, `vmk`, `vmcp`).
  - `common/base_imgs/`: Target directory where prepared `.qcow2` virtual machine disk images must reside.
  - `common/ssh/`: Target directory for generated test SSH keys (`ida_rsa`, `ida_rsa.pub`).
  - `common/bin/`: Static helper tools (e.g., `toybox`) and test binaries.
  - `common/qemu/`: Statically linked QEMU binary (`qemu-system-x86_64`) and firmware (`pc-bios/`).
  - `common/tests/`: Automated test scripts and reproducers.
- `scripts/`: Workstation image preparation tools and guest initialization drop-ins (`prep_base_image.py`, `virt_init.sh`).

## External Binary Dependencies

`virt` executes standalone test environments and offline VMs by bundling static binaries inside `common/`:

- **QEMU & BIOS (`common/qemu/`)**: Must contain a statically linked QEMU executable (`qemu-system-x86_64`) and its corresponding `pc-bios/` firmware directory.
- **Helper Utilities (`common/bin/`) (Optional)**: Can contain optional static utilities such as `toybox`. If present, `prep-host.sh` automatically links fallback applets (`timeout`, `base64`) on stripped-down test machines.

## Base Workflow Guide

### 1. Generate SSH Keys
Before preparing VM disk images, create the identity directory and generate a test key:
```bash
mkdir -p common/ssh && ssh-keygen -t rsa -f common/ssh/ida_rsa -N ""
```

### 2. Prepare a Base Disk Image
Download a standard Linux cloud image (e.g., `ubuntu-24.04-server-cloudimg-amd64.img`) and prepare it offline:
```bash
scripts/prep_base_image.py -i ubuntu.img -o common/base_imgs/ubuntu_base.qcow2 -sk common/ssh/ida_rsa.pub
```
**What this does**: Converts the raw cloud image to `.qcow2`, uninstalls conflicting cloud-init services, injects your generated SSH public key for root login, and sets up serial console autologin. Prepared disk images must be placed in `common/base_imgs/`.

### 3. Synchronize to Remote Host (Optional)
If running tests on a separate remote machine from your workstation, use `dsync.py` to transfer workspace scripts and images:
```bash
common/scripts/dsync.py -m $HOSTNAME
```
*(Skip this step if developing and testing on the same machine).*

### 4. Deploy & Interact

Deploy and start a standard VM instance:
```bash
vm.py run vm1
```

, or use the shorthand:
```bash
vmr vm1
```

You can specify the number of CPUs and memory sizes (among other things):
```bash
vmr vm1 --smp 4 --memory 8G
```

SSH into a running VM:
```bash
vms vm1
```

Copy files to or from a VM:
```bash
vmcp vm1:/var/log/syslog ./guest_syslog
```

Terminate a running VM:
```bash
vmk vm1
```

## Custom Kernel Testing

When iterating on custom Linux kernel builds, `dsync.py` can synchronize strictly necessary boot binaries rather than full source trees.

### 1. Synchronize Compiled Kernel (Optional)
If testing on a remote machine, transfer your compiled kernel binaries (built out-of-tree):
```bash
common/scripts/dsync.py -k kernel_directory_name -ks /path/to/builds -m test_host
```

### 2. Boot VM with Custom Kernel
Launch a VM instance executing your specific kernel binary and custom boot parameters:
```bash
vmr test -k my_kernel -cmd 'slub_debug=FZP'
```
