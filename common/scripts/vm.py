#!/usr/bin/env python3

import argparse
import re
import logging
import math
import pathlib
import os
import subprocess
import shlex
import signal
import sys
import termios
import time

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


def in_vm():
    """Return True if running inside a QEMU guest VM."""
    vendor_path = pathlib.Path("/sys/class/dmi/id/sys_vendor")
    return vendor_path.exists() and "QEMU" in vendor_path.read_text()


def qualify_vm_name(name):
    """Derive nested VM uniqueness by using the parent hostname as a prefix."""
    if not in_vm():
        return name

    product_path = pathlib.Path("/sys/class/dmi/id/product_name")
    if not product_path.exists():
        logging.error("Running inside QEMU guest, but SMBIOS product_name table is missing.")
        sys.exit(1)

    parent_name = product_path.read_text().strip()
    return f"{parent_name}-{name}" if parent_name else name


def get_vm_pid(name):
    """Locate local QEMU process PID using the VM name (used as the product_name) """
    res = subprocess.run(['pgrep', '-f', f'product={name}([, ]|$)'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if res.returncode != 0:
        return None

    pids = [int(p) for p in res.stdout.split()]
    # When QEMU daemonizes (-daemonize), the initial parent forks a background child and exits.
    # For a brief window before the parent is reaped, pgrep may match both. Since child PIDs
    # are sequentially higher than parent PIDs, max() deterministically selects the daemon.
    return max(pids)


def get_running_vms():
    """Find and return list of (pid, vm_name) for all running QEMU VMs."""
    res = subprocess.run(['pgrep', '-f', 'qemu-system'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, universal_newlines=True)
    if res.returncode != 0:
        return []
    vms = []
    for pid in res.stdout.split():
        cmdline = (pathlib.Path('/proc') / pid / 'cmdline').read_text().replace('\x00', ' ')
        name = re.search(r'product=([^, ]+)', cmdline).group(1)
        vms.append((pid, name))
    return vms


def cmd_list(args):
    vms = get_running_vms()
    if not vms:
        print("No running VMs found.")
        return
    print(f"{'PID':<8} {'VM Name':<30}")
    print("-" * 40)
    for pid, name in sorted(vms, key=lambda x: x[1]):
        print(f"{pid:<8} {name:<30}")


def cmd_kill(args):
    pid = get_vm_pid(args.name)
    if not pid:
        logging.error("Error: VM '%s' is not running.", args.name)
        sys.exit(1)
    os.kill(pid, signal.SIGTERM)
    print(f"Terminated VM '{args.name}'")


def cmd_ssh(args):
    ipv6 = vmaddr.vm_name_to_ipv6_local(args.name)
    target = f"root@{ipv6}%{BRIDGE_IFACE_NAME}"
    identity_file = find_ssh_identity_file()
    ssh_cmd = ['ssh']
    if args.verbose:
        ssh_cmd.append('-v')
    else:
        ssh_cmd.extend(['-q', '-o', 'LogLevel=QUIET'])
    ssh_cmd.extend([
        '-i', str(identity_file),
        '-o', f'ConnectTimeout={args.timeout}',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'IPQoS=none',
        target,
    ] + args.ssh_args)
    os.execvp('ssh', ssh_cmd)


def expand_scp_target(arg):
    if ':' not in arg or arg.startswith('-'):
        return arg

    vm_name, path_part = arg.split(':', 1)
    qualified_name = qualify_vm_name(vm_name)
    ipv6 = vmaddr.vm_name_to_ipv6_local(qualified_name)
    return f"root@[{ipv6}%{BRIDGE_IFACE_NAME}]:{path_part}"


def cmd_scp(args):
    identity_file = find_ssh_identity_file()
    scp_cmd = ['scp']
    if args.verbose:
        scp_cmd.append('-v')
    else:
        scp_cmd.extend(['-q', '-o', 'LogLevel=QUIET'])

    expanded_args = [expand_scp_target(a) for a in args.scp_args]
    scp_cmd.extend([
        '-i', str(identity_file),
        '-o', f'ConnectTimeout={args.timeout}',
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'IPQoS=none',
    ] + expanded_args)
    os.execvp('scp', scp_cmd)


def pin_vm_vcpus(name, smp, start_cpu=0):
    """Pin QEMU vCPU threads 1:1 to physical host CPUs."""
    pid = get_vm_pid(name)
    if not pid:
        return

    tids = []
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            tids = sorted(int(p.name) for p in pathlib.Path(f'/proc/{pid}/task').iterdir())
            if len(tids) > smp:
                break
        except Exception:
            pass
        time.sleep(0.05)

    total_cpus = os.cpu_count() or 1
    for i, tid in enumerate(tids[1 : smp + 1]):
        try:
            os.sched_setaffinity(tid, {(start_cpu + i) % total_cpus})
        except Exception:
            pass


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
            # Pass VM name in SMBIOS DMI tables, used by the guest to set the hostname
            # and used by this script to find VM PIDs and parent VM names.
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
        proc = subprocess.Popen(command)
        if args.daemonize:
            proc.wait()
        if not in_vm():
            pin_vm_vcpus(args.name, args.smp, args.pin_start_cpu)
        if not args.daemonize:
            proc.wait()
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
    run_parser.add_argument('--pin-start-cpu', type=int, default=0, help='Starting host CPU index to pin vCPUs')
    run_parser.set_defaults(func=cmd_run)

    list_parser = subparsers.add_parser('list', parents=[base_parser], help='List all running VMs')
    list_parser.set_defaults(func=cmd_list)

    kill_parser = subparsers.add_parser('kill', parents=[base_parser], help='Kill a running VM')
    kill_parser.add_argument('name', type=str, help='VM name')
    kill_parser.set_defaults(func=cmd_kill)

    ssh_parser = subparsers.add_parser('ssh', parents=[base_parser], help='SSH into a running VM')
    ssh_parser.add_argument('--timeout', type=int, default=15, help='SSH connection timeout in seconds')
    ssh_parser.add_argument('name', type=str, help='VM name')
    ssh_parser.add_argument('ssh_args', nargs=argparse.REMAINDER, help='Extra SSH arguments')
    ssh_parser.set_defaults(func=cmd_ssh)

    scp_desc = (
        "Transfer files between host and VMs or directly between two VMs.\n\n"
        "Examples:\n"
        "  vm.py scp vm1:/root/test.txt .\n"
        "  vm.py scp -r ./artifacts vm1:/tmp/\n"
        "  vm.py scp vm1:/var/log/syslog vm2:/tmp/vm1_syslog"
    )
    scp_parser = subparsers.add_parser('scp', parents=[base_parser],
                                       formatter_class=argparse.RawDescriptionHelpFormatter,
                                       help='SCP files to/from a running VM',
                                       description=scp_desc)
    scp_parser.add_argument('--timeout', type=int, default=15, help='SCP connection timeout in seconds')
    scp_parser.add_argument('scp_args', nargs=argparse.REMAINDER, help='Extra SCP arguments')
    scp_parser.set_defaults(func=cmd_scp)

    args = parser.parse_args()
    if hasattr(args, 'name'):
        args.name = qualify_vm_name(args.name)
    logging.basicConfig(format='%(message)s', level=logging.INFO if args.verbose else logging.WARNING)
    args.func(args)


if __name__ == '__main__':
    main()
