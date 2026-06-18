#!/usr/bin/env python3

import argparse
import logging
import math
import pathlib
import os
import subprocess
import shlex
import sys
import termios

import vmaddr
import utils

BIOS_DIR_NAME = 'pc-bios'
BASE_IMGS_DIR_NAME = 'base_imgs'
COMMON_DIR_NAME = 'common'
KERNEL_BINARY_NAME = 'bzImage'
QEMU_BINARY_NAME = 'qemu-system-x86_64'
BRIDGE_IFACE_NAME = 'br_virt'
SSH_IDENTITY_FILE_NAME = 'ida_rsa'

DEFAULT_MEMORY_BYTES = (4 << 30) # 4G

# VT100 escape codes to reset terminal emulator software state upon exit:
# \033[?7h  = DECAWM: Re-enable auto-wrapping
# \033[?25h = DECTCEM: Show cursor
# \033[0m   = SGR 0: Reset text colors
VT100_RESET = '\033[?7h\033[?25h\033[0m\r'


def save_host_termios():
    try:
        return termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        return None


def restore_host_termios(old_termios):
    if old_termios is not None:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_termios)


def find_bios_dir():
    return utils.find_path(BIOS_DIR_NAME, True, 'bios dir')


def find_base_image():
    base_imgs_dir = utils.find_path(BASE_IMGS_DIR_NAME, True, 'base images dir')
    return utils.find_path('*.qcow2', False, 'base qcow2 image', parent=base_imgs_dir, recursive=False)


def find_qemu_binary():
    return utils.find_path(QEMU_BINARY_NAME, False, 'QEMU binary')


def find_common_dir():
    return utils.find_path(COMMON_DIR_NAME, True, 'Common dir', recursive=False)


def find_ssh_identity_file():
    return utils.find_path(SSH_IDENTITY_FILE_NAME, False, 'SSH identity file')


def calculate_memory():
	# Find the amount of free memory
	free_bytes = None
	with open('/proc/meminfo', 'r') as file:
		for line in file:
			if 'MemFree' in line:
				free_bytes = int(line.split()[1]) << 10
	
	if free_bytes is None:
		print('Could not get the amount of free memory')
		exit(-1)

	# If the default size cannot be used, find the nearest power of 2.
	# Using powers of 2 keeps the memory sizes non-arbitrary.
	vm_bytes = DEFAULT_MEMORY_BYTES
	if vm_bytes > free_bytes:
		vm_bytes = int(2 ** math.log2(free_bytes))

	# Convert to string format
	if vm_bytes > (1 << 30):
		vm_bytes = str(vm_bytes >> 30) + 'G'
	elif vm_bytes > (1 << 20):
		vm_bytes = str(vm_bytes >> 20) + 'M'

	logging.info('Setting VM memory size to %s', vm_bytes)
	return vm_bytes


def qualify_vm_name(name):
    vendor_path = pathlib.Path("/sys/class/dmi/id/sys_vendor")
    if not vendor_path.exists() or "QEMU" not in vendor_path.read_text():
        return name

    product_path = pathlib.Path("/sys/class/dmi/id/product_name")
    if not product_path.exists():
        logging.error("Running inside QEMU guest, but SMBIOS product_name table is missing.")
        sys.exit(1)

    parent_name = product_path.read_text().strip()
    return f"{parent_name}-{name}" if parent_name else name


def cmd_kill(args):
    res = subprocess.run(['pkill', '-f', f'product={args.name}'])
    if res.returncode == 0:
        print(f"Terminated VM '{args.name}'")
    else:
        print(f"No running QEMU process found for VM '{args.name}'")


def cmd_ssh(args):
    ipv6 = vmaddr.vm_name_to_ipv6_local(args.name)
    target = f"root@{ipv6}%{BRIDGE_IFACE_NAME}"
    identity_file = find_ssh_identity_file()
    ssh_cmd = ['ssh']
    if args.verbose:
        ssh_cmd.append('-v')
    else:
        ssh_cmd.extend(['-q', '-o', 'LogLevel=QUIET'])
    ssh_cmd.extend(['-i', str(identity_file), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'IPQoS=none', target] + args.ssh_args)
    os.execvp('ssh', ssh_cmd)


def cmd_run(args):
    memory = args.memory if args.memory else calculate_memory()
    bios_dir = find_bios_dir()
    img = args.img if args.img else find_base_image()
    mac_address = vmaddr.vm_name_to_mac(args.name)

    qemu_args = [
            '-machine'	, str(args.machine),
            '-cpu'		, str(args.cpu),
            '-smp'		, str(args.smp),
            '-m'		, memory,
            '-L'		, str(bios_dir),
            # Pass VM name in SMBIOS DMI tables so guest virt_init.sh can dynamically set hostname
            '-smbios'	, f'type=1,product={args.name}',
            '-drive'	, 'file={},format={},if=none,id=drive'.format(img, args.format),
            '-device'	, 'virtio-blk-pci,drive=drive,id=virtblk',
            ]

    if not args.persistent:
        qemu_args += ['-snapshot']

    qemu_args += ['-daemonize'] if args.daemonize else ['-nographic']

    if not args.no_kvm:
        qemu_args += ['-enable-kvm']

    if args.network == 'tap':
        ifname = f"tap_{args.name}"[:15]
        ifup_script = pathlib.Path(__file__).resolve().parent / 'ifup.sh'
        qemu_args += [
                '-netdev'   , f'tap,id=net0,ifname={ifname},script={ifup_script},downscript=no',
                '-device'   , 'virtio-net-pci,netdev=net0,mac={}'.format(mac_address),
            ]
    elif args.network:
        print('Only tap networking is supported')
        exit(-1)
   
    if args.kernel:
        search_dir = args.kernel_search_dir if args.kernel_search_dir else find_common_dir()
        kernel_dir = utils.resolve_kernel_dir(args.kernel, search_dir)
        kernel_binary = utils.find_kernel_binary(kernel_dir, args.kernel_binary)
        modules_dir = utils.find_modules_dir(kernel_dir)
        cmdline = args.kernel_cmdline
        if 'root=' not in cmdline:
            cmdline += ' root=/dev/vda1'
        if 'console=' not in cmdline:
            cmdline += ' console=ttyS0'
        qemu_args += [
                '-kernel'	, str(kernel_binary),
                '-append'	, cmdline,
                '-bios'		, 'qboot.rom',  # qboot is faster and does not mess up the terminal
                '-fsdev'	, 'local,path={},security_model=passthrough,readonly=on,id=fsdev-kmods'.format(modules_dir),
                '-device'	, 'virtio-9p-pci,fsdev=fsdev-kmods,mount_tag=virt_kmods',
                ]


    common_dir = find_common_dir()
    if common_dir:
        common_path = pathlib.Path(common_dir).resolve()
        repo_root = common_path.parent

        qemu_args += [
                '-fsdev'	, f'local,path={repo_root},security_model=passthrough,readonly=on,id=fsdev-root',
                '-device'	, 'virtio-9p-pci,fsdev=fsdev-root,mount_tag=virt_root',
                ]

    command = [str(find_qemu_binary())] + qemu_args
    if args.extra_args:
        command += shlex.split(args.extra_args)

    if args.dry_run:
        print('QEMU command:', ' '.join(command))
        return

    old_termios = save_host_termios()
    try:
        subprocess.run(command)
    finally:
        print(VT100_RESET, end='', flush=True)
        restore_host_termios(old_termios)


def main():
    base_parser = argparse.ArgumentParser(add_help=False)
    base_parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose debugging output')

    parser = argparse.ArgumentParser(prog='vm.py', parents=[base_parser],
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='subcommand', help='Subcommands')
    subparsers.required = True

    run_parser = subparsers.add_parser('run', parents=[base_parser], help='Run a VM',
                                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    run_parser.add_argument('name', type=str, help='VM name')
    run_parser.add_argument('-i', '--img', type=str, help='Path to image')
    run_parser.add_argument('-m', '--memory', type=str, help='Memory size')
    run_parser.add_argument('-k', '--kernel', type=str, help='Specific kernel name or path to run')
    run_parser.add_argument('-ks', '--kernel-search-dir', default=None, help='Parent directory to search for kernel builds (default: common directory)')
    run_parser.add_argument('--kernel-binary', default='bzImage', help='Kernel binary executable filename')
    run_parser.add_argument('-cmd', '--kernel-cmdline', type=str, default='', help='Kernel command line')
    run_parser.add_argument('-s', '--smp', type=int, default=2, help='Number of vCPUs')
    run_parser.add_argument('-c', '--cpu', type=str, default='host', help='QEMU "-cpu" arg')
    run_parser.add_argument('-n', '--network', type=str, default='tap', help='VM network type')
    run_parser.add_argument('-p', '--persistent', action='store_true', help='Run VM persistently (do not use -snapshot)')
    run_parser.add_argument('-d', '--daemonize', action='store_true', help='Whether to deamonize QEMU')
    run_parser.add_argument('--machine', type=str, default='type=q35', help='QEMU "-machine" arg')
    run_parser.add_argument('--format', type=str, default='qcow2', help='Image format')
    run_parser.add_argument('--no-kvm', action='store_true', help='Do not use KVM')
    run_parser.add_argument('--dry-run', action='store_true', help='Create the QEMU command only')
    run_parser.add_argument('--extra-args', type=str, help='Extra args to pass to QEMU')
    run_parser.set_defaults(func=cmd_run)

    kill_parser = subparsers.add_parser('kill', parents=[base_parser], help='Kill a running VM')
    kill_parser.add_argument('name', type=str, help='VM name')
    kill_parser.set_defaults(func=cmd_kill)

    ssh_parser = subparsers.add_parser('ssh', parents=[base_parser], help='SSH into a running VM')
    ssh_parser.add_argument('name', type=str, help='VM name')
    ssh_parser.add_argument('ssh_args', nargs=argparse.REMAINDER, help='Extra SSH arguments')
    ssh_parser.set_defaults(func=cmd_ssh)

    args = parser.parse_args()
    args.name = qualify_vm_name(args.name)
    logging.basicConfig(format='%(message)s', level=logging.INFO if args.verbose else logging.WARNING)
    args.func(args)


if __name__ == '__main__':
    main()
