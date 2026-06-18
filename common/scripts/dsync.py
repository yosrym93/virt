#!/usr/bin/env python3

import argparse
import getpass
import pathlib
import subprocess
import sys
import utils

SSH_OPTS = ['-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR']


def rsync(*args, delete=False, excludes=None):
    ssh_rsh = 'ssh ' + ' '.join(SSH_OPTS)
    cmd = ['rsync', '-az', '--progress', '-e', ssh_rsh]
    if delete:
        cmd.append('--delete')
    if excludes:
        for ex in excludes:
            cmd.extend(['--exclude', ex])
    cmd.extend([str(a) for a in args])
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def resolve_kernel_dir(kernel_arg, bin_name):
    # Stage 1: Check if kernel_arg is an explicit absolute or relative path
    p = pathlib.Path(kernel_arg).expanduser()
    if p.exists() and p.is_dir() and utils.find_path(bin_name, False, 'Kernel binary', parent=p, allow_zero=True):
        return p.resolve()

    # Stage 2: If kernel_arg is just a build folder name, search home directory for it
    res = utils.find_path(kernel_arg, True, 'Kernel build directory', parent=pathlib.Path.home())
    return pathlib.Path(res).resolve()


def main():
    parser = argparse.ArgumentParser(prog='dsync.py',
                                     description='Synchronize local virt workspace with a remote development machine',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('machine', help='Remote target host machine (e.g. mymachine)')
    parser.add_argument('-k', '--kernel', type=str, help='Specific kernel name or path to synchronize (skips full workspace sync)')
    parser.add_argument('--kernel-binary', default='bzImage', help='Kernel binary executable filename to search for')
    parser.add_argument('-p', '--remote-path', type=str, help='Override remote destination repository path')
    args = parser.parse_args()

    user = getpass.getuser()
    remote_repo = args.remote_path if args.remote_path else f"/data/{user}/virt"
    ssh_host = f"root@{args.machine}"

    if args.kernel:
        kernel_dir = resolve_kernel_dir(args.kernel, args.kernel_binary)
        name = kernel_dir.name
        print(f"=== Synchronizing kernel build '{name}' to {args.machine} ===")
        remote_kernel_dir = f"{remote_repo}/common/kernel/{name}"
        subprocess.run(['ssh'] + SSH_OPTS + [ssh_host, f"mkdir -p {remote_kernel_dir}"], check=True)

        kernel_bin = utils.find_path(args.kernel_binary, False, 'Kernel binary', parent=kernel_dir)
        modules = utils.find_path('lib', True, 'Kernel modules', parent=kernel_dir, allow_zero=True)
        selftests = utils.find_path('selftests', True, 'Kernel selftests', parent=kernel_dir, allow_zero=True)

        srcs = [kernel_bin]
        if modules:
            srcs.append(modules)
        if selftests:
            srcs.append(selftests)

        rsync(*srcs, f"{ssh_host}:{remote_kernel_dir}/", delete=True)
        return

    print(f"=== Synchronizing repository workspace to {args.machine} ===")
    subprocess.run(['ssh'] + SSH_OPTS + [ssh_host, f"mkdir -p {remote_repo}"], check=True)

    common_dir = utils.find_path('common', True, 'Common directory')
    repo_root = pathlib.Path(common_dir).resolve().parent
    rsync(repo_root / 'common', f"{ssh_host}:{remote_repo}/", delete=False, excludes=['imgs', 'imgs/*'])
    rsync(repo_root / 'scripts', f"{ssh_host}:{remote_repo}/", delete=True)

    print(f"=== Executing prep-host.sh on {args.machine} ===")
    prep_script = f"{remote_repo}/common/scripts/prep-host.sh"
    subprocess.run(['ssh'] + SSH_OPTS + [ssh_host, prep_script], check=True)


if __name__ == '__main__':
    main()
