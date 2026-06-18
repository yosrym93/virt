#!/usr/bin/env python3

import argparse
import os
import pathlib
import shutil
import subprocess
import sys


INIT_SCRIPT_NAME = 'virt_init.sh'
INIT_SERVICE_NAME = 'virt-init.service'
SERIAL_AUTOLOGIN_CONF_NAME = 'serial_autologin.conf'


def check_required_tools():
    for tool in ['qemu-img', 'virt-customize']:
        if not shutil.which(tool):
            print(f"Error: Required CLI tool '{tool}' is not installed or not in PATH.")
            sys.exit(1)


def main():
    check_required_tools()

    parser = argparse.ArgumentParser(prog='prep_base_image.py',
                                     description='Prepare a stock Linux cloud image for virtualization workflow',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i', '--input', type=str, required=True, help='Path to downloaded stock cloud image (e.g. ubuntu.img)')
    parser.add_argument('-o', '--output', type=str, required=True, help='Target path for prepared base image (e.g. common/base_imgs/base.qcow2)')
    parser.add_argument('-sk', '--ssh-pubkey', type=str, required=True, help='Path to SSH public key to inject into authorized_keys')
    parser.add_argument('-f', '--force', action='store_true', help='Overwrite output image if it already exists')
    args = parser.parse_args()

    stock_img = pathlib.Path(args.input).resolve()
    if not stock_img.exists():
        print(f"Error: Stock image '{stock_img}' does not exist.")
        sys.exit(1)

    output_img = pathlib.Path(args.output).resolve()
    if output_img.exists():
        if args.force:
            print(f"Removing existing output image at '{output_img}'")
            output_img.unlink()
        else:
            print(f"Error: Output image '{output_img}' already exists. Use -f/--force to overwrite.")
            sys.exit(1)

    pubkey = pathlib.Path(args.ssh_pubkey).resolve()
    if not pubkey.is_file():
        print(f"Error: SSH pubkey file '{pubkey}' does not exist or is not a file.")
        sys.exit(1)

    current_dir = pathlib.Path(__file__).resolve().parent
    init_script = current_dir / INIT_SCRIPT_NAME
    if not init_script.exists():
        print(f"Error: Init script not found at '{init_script}'")
        sys.exit(1)

    init_service = current_dir / INIT_SERVICE_NAME
    if not init_service.exists():
        print(f"Error: Init service unit not found at '{init_service}'")
        sys.exit(1)

    autologin_conf = current_dir / SERIAL_AUTOLOGIN_CONF_NAME
    if not autologin_conf.exists():
        print(f"Error: Serial autologin unit not found at '{autologin_conf}'")
        sys.exit(1)

    output_img.parent.mkdir(parents=True, exist_ok=True)

    print(f"Converting '{stock_img}' to qcow2 at '{output_img}'...")
    subprocess.run(['qemu-img', 'convert', '-O', 'qcow2', str(stock_img), str(output_img)], check=True)

    print(f"Customizing base image '{output_img}' via virt-customize...")

    customize_cmd = [
        'virt-customize', '-a', str(output_img),
        '--mkdir', '/etc/systemd/system/serial-getty@ttyS0.service.d',
        '--ssh-inject', f'root:file:{pubkey}',
        '--upload', f'{init_script}:/usr/local/bin/virt_init.sh',
        '--upload', f'{init_service}:/etc/systemd/system/virt-init.service',
        '--upload', f'{autologin_conf}:/etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf',
        '--run-command', 'systemctl enable virt-init.service',
    ]

    subprocess.run(customize_cmd, check=True)
    print("\nBase image prepared successfully!")
    print(f"Output: {output_img}")


if __name__ == '__main__':
    main()
