#!/usr/bin/env python3

import argparse
import math
import pathlib
import os
import subprocess
import shlex

import vmaddr
import utils

BIOS_DIR_NAME = 'pc-bios'
IMGS_DIR_NAME = 'imgs'
COMMON_DIR_NAME = 'common'
KERNEL_BINARY_NAME = 'bzImage'
QEMU_BINARY_NAME = 'qemu-system-x86_64'

DEFAULT_MEMORY_BYTES = (4 << 30) # 4G


def find_bios_dir():
    return utils.find_path(BIOS_DIR_NAME, True, 'bios dir')


def find_image(name):
    pattern = os.path.join(IMGS_DIR_NAME, '*{}*'.format(name))
    return utils.find_path(pattern, False, 'compatible image')
	

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


def main():
    parser = argparse.ArgumentParser(prog='vm.py', usage='%(prog)s [options]',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)	
    parser.add_argument('name', type=str, help='VM name')
    parser.add_argument('-i', '--img', type=str, help='Path to image')
    parser.add_argument('-m', '--memory', type=str)
    parser.add_argument('-k', '--kernel-dir', type=str, help='Path to kernel directory')
    parser.add_argument('-cmd', '--kernel-cmdline', type=str, default='', help='Kernel command line')
    parser.add_argument('-s', '--smp', type=int, default=2, help='Number of vCPUs')
    parser.add_argument('-c', '--cpu', type=str, default='host', help='QEMU "-cpu" arg')
    parser.add_argument('-n', '--network', type=str, default='tap', help='VM network type')
    parser.add_argument('-d', '--daemonize', action='store_true', help='Whether to deamonize QEMU')
    parser.add_argument('--machine', type=str, default='type=q35', help='QEMU "-machine" arg')
    parser.add_argument('--format', type=str, default='qcow2', help='Image format')
    parser.add_argument('--no-kvm', action='store_true', help='Do not use KVM')
    parser.add_argument('--dry-run', action='store_true', help='Create the QEMU command only')
    parser.add_argument('--extra-args', type=str, help='Extra args to pass to QEMU')
    args = parser.parse_args()

    memory = args.memory if args.memory else calculate_memory()
    bios_dir = find_bios_dir()
    img = args.img if args.img else find_image(args.name)
    mac_address = vmaddr.vm_name_to_mac(args.name)

    qemu_args = [
            '-machine'	, str(args.machine),
            '-cpu'		, str(args.cpu),
            '-smp'		, str(args.smp),
            '-m'		, memory,
            '-L'		, str(bios_dir),
            '-drive'	, 'file={},format={},if=none,id=drive'.format(img, args.format),
            '-device'	, 'virtio-blk-pci,drive=drive,id=virtblk',
            ]

    qemu_args += ['-daemonize'] if args.daemonize else ['-nographic']

    if not args.no_kvm:
        qemu_args += ['-enable-kvm']

    if args.network == 'tap':
        qemu_args += [
                '-netdev'   , 'tap,id=net0,ifname=tap0,script=no,downscript=no',
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
                '-fsdev'	, 'local,path={},security_model=passthrough,readonly=on,id=mod9p'.format(modules_dir),
                '-device'	, 'virtio-9p-pci,fsdev=mod9p,mount_tag=kmodules',
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
    else:
        subprocess.run(command)


if __name__ == '__main__':
    main()
