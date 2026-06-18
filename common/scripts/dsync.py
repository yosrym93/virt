#!/usr/bin/env python3

import argparse
import getpass
import logging
import pathlib
import subprocess
import sys
import utils

SSH_OPTS = ['-o', 'StrictHostKeyChecking=no', '-o', 'UserKnownHostsFile=/dev/null', '-o', 'LogLevel=ERROR']


def rsync(*args, delete=False, excludes=None, copy_links=False):
    ssh_rsh = 'ssh ' + ' '.join(SSH_OPTS)
    cmd = ['rsync', '-az', '--progress', '-e', ssh_rsh]
    if copy_links:
        cmd.append('--copy-links')
    if delete:
        cmd.append('--delete')
    if excludes:
        for ex in excludes:
            cmd.extend(['--exclude', ex])
    cmd.extend([str(a) for a in args])
    logging.info("+ %s", ' '.join(cmd))
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser(prog='dsync.py',
                                     description='Synchronize local virt workspace with a remote development machine',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('machine', help='Remote target host machine (e.g. mymachine)')
    parser.add_argument('-k', '--kernel', type=str, help='Specific kernel name or path to synchronize (skips full workspace sync)')
    parser.add_argument('-ks', '--kernel-search-dir', default='~/builds', help='Parent directory to search for kernel builds')
    parser.add_argument('--kernel-binary', default='bzImage', help='Kernel binary executable filename to search for')
    parser.add_argument('-p', '--remote-path', type=str, help='Override remote destination repository path')
    parser.add_argument('-v', '--verbose', action='store_true', help='Enable verbose execution and debugging output')
    args = parser.parse_args()

    logging.basicConfig(format='%(message)s', level=logging.INFO if args.verbose else logging.WARNING)

    user = getpass.getuser()
    remote_repo = args.remote_path if args.remote_path else f"/data/{user}/virt"
    ssh_host = f"root@{args.machine}"

    if args.kernel:
        kernel_dir = utils.resolve_kernel_dir(args.kernel, args.kernel_search_dir)
        name = kernel_dir.name
        print(f"=== Synchronizing kernel build '{name}' to {args.machine} ===")
        remote_kernel_dir = f"{remote_repo}/common/kernel/{name}"
        subprocess.run(['ssh'] + SSH_OPTS + [ssh_host, f"mkdir -p {remote_kernel_dir}"], check=True)

        kernel_bin = utils.find_kernel_binary(kernel_dir, args.kernel_binary)
        modules_dir = utils.find_modules_dir(kernel_dir)
        selftests = utils.find_path('selftests', True, 'Kernel selftests', parent=kernel_dir, recursive=False, allow_zero=True)

        srcs = [kernel_bin]
        if modules_dir:
            srcs.append(modules_dir.parent.parent)
        if selftests:
            srcs.append(selftests)

        rsync(*srcs, f"{ssh_host}:{remote_kernel_dir}/", delete=True, copy_links=True)
        return

    print(f"=== Synchronizing repository workspace to {args.machine} ===")
    subprocess.run(['ssh'] + SSH_OPTS + [ssh_host, f"mkdir -p {remote_repo}"], check=True)

    common_dir = utils.find_path('common', True, 'Common directory')
    repo_root = pathlib.Path(common_dir).resolve().parent
    rsync(repo_root / 'common', f"{ssh_host}:{remote_repo}/", delete=False)

    print(f"=== Executing prep-host.sh on {args.machine} ===")
    prep_script = f"{remote_repo}/common/scripts/prep-host.sh"
    cmd = ['ssh'] + SSH_OPTS + [ssh_host, prep_script]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if args.verbose or res.returncode != 0:
        print(res.stdout, end='', file=sys.stderr if res.returncode != 0 else sys.stdout)
    if res.returncode != 0:
        sys.exit(res.returncode)


if __name__ == '__main__':
    main()
