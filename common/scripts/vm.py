#!/usr/bin/env python3

import argparse
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
IMGS_DIR_NAME = 'imgs'
COMMON_DIR_NAME = 'common'
KERNEL_BINARY_NAME = 'bzImage'
QEMU_BINARY_NAME = 'qemu-system-x86_64'

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


def find_kernel_binary(kernel_dir):
    return utils.find_path(KERNEL_BINARY_NAME, False, 'kernel binary (bzImage)',
                     parent=kernel_dir, allow_dup=True)


def find_modules_dir(kernel_dir):
    pattern = os.path.join('lib', 'modules', '*')
    return utils.find_path(pattern, True, 'modules dir',
                     parent=kernel_dir)

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

	print('Setting VM memory size to {}'.format(vm_bytes))
	return vm_bytes


def get_tap_iface(vm_name):
    return f"tap_{vm_name}"[:15]


def cmd_kill(args):
    res = subprocess.run(['pkill', '-f', f'product={args.name}'])
    if res.returncode == 0:
        print(f"Terminated VM '{args.name}'")
    else:
        print(f"No running QEMU process found for VM '{args.name}'")


def cmd_ssh(args):
    iface = get_tap_iface(args.name)
    ipv6 = vmaddr.vm_name_to_ipv6_local(args.name)
    target = f"root@{ipv6}%{iface}"
    common_dir = find_common_dir()
    identity_file = pathlib.Path(common_dir) / 'ssh' / 'ida_rsa'
    ssh_cmd = ['ssh', '-i', str(identity_file), '-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR', target] + args.ssh_args
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
        ifname = get_tap_iface(args.name)
        ifup_script = pathlib.Path(__file__).resolve().parent / 'ifup.sh'
        qemu_args += [
                '-netdev'   , f'tap,id=net0,ifname={ifname},script={ifup_script},downscript=no',
                '-device'   , 'virtio-net-pci,netdev=net0,mac={}'.format(mac_address),
            ]
    elif args.network:
        print('Only tap networking is supported')
        exit(-1)
   
    if args.kernel_dir:
        kernel_binary = find_kernel_binary(args.kernel_dir)
        modules_dir = find_modules_dir(args.kernel_dir)
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
        imgs_dir = common_path / IMGS_DIR_NAME
        imgs_dir.mkdir(parents=True, exist_ok=True)

        qemu_args += [
                '-fsdev'	, f'local,path={repo_root},security_model=passthrough,readonly=on,id=fsdev-root',
                '-device'	, 'virtio-9p-pci,fsdev=fsdev-root,mount_tag=virt_root',
                '-fsdev'	, f'local,path={imgs_dir},security_model=passthrough,readonly=off,id=fsdev-imgs',
                '-device'	, 'virtio-9p-pci,fsdev=fsdev-imgs,mount_tag=virt_imgs',
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
    parser = argparse.ArgumentParser(prog='vm.py',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    subparsers = parser.add_subparsers(dest='subcommand', required=True, help='Subcommands')

    run_parser = subparsers.add_parser('run', help='Run a VM',
                                       formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    run_parser.add_argument('name', type=str, help='VM name')
    run_parser.add_argument('-i', '--img', type=str, help='Path to image')
    run_parser.add_argument('-m', '--memory', type=str, help='Memory size')
    run_parser.add_argument('-k', '--kernel-dir', type=str, help='Path to kernel directory')
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

    kill_parser = subparsers.add_parser('kill', help='Kill a running VM')
    kill_parser.add_argument('name', type=str, help='VM name')
    kill_parser.set_defaults(func=cmd_kill)

    ssh_parser = subparsers.add_parser('ssh', help='SSH into a running VM')
    ssh_parser.add_argument('name', type=str, help='VM name')
    ssh_parser.add_argument('ssh_args', nargs=argparse.REMAINDER, help='Extra SSH arguments')
    ssh_parser.set_defaults(func=cmd_ssh)

    args = parser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
