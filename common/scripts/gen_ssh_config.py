#!/usr/bin/env python3

import argparse
import pathlib
import os

import utils
import vmaddr


IDENTITY_FILE_NAME = 'ida_rsa'


class VM:
    def __init__(self, name, parent):
        self.name = name
        self.parent = parent

    def __repr__(self):
        return '<VM: {}, parent: {}>'.format(
                self.name,
                self.parent.name if self.parent else 'None')


def gen_vm_config(vm, identity_file):
    ip_addr = vmaddr.vm_name_to_ipv6_local(vm.name)

    config = ''
    config += 'Host {}\n'.format(vm.name)
    config += '  HostName {}%%tap0\n'.format(ip_addr)
    config += '  User root\n'
    config += '  IdentityFile {}\n'.format(identity_file)
    if vm.parent:
        config += '  ProxyJump {}\n'.format(vm.parent.name)
    config += '\n'
    return config


def find_identity_file():
    pattern = os.path.join('ssh', IDENTITY_FILE_NAME)
    return utils.find_path(pattern, False, 'SSH identity file')


def find_ssh_config_file(path):
    return utils.find_path(path, False, 'SSH config', allow_zero=True, parent=pathlib.Path.home())


def write_config(config_file, config):
        with open(config_file, 'w+') as f:
            print('Writing new config')
            f.write(config)


def main():
    parser = argparse.ArgumentParser(prog='gen_ssh_config.py',
                                     usage='%(prog)s [options]',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('ssh_paths', type=str, nargs='+', help='VM SSH pathsi (e.g. l1 l1,l2)')
    parser.add_argument('-o', '--overwrite', action='store_true', help='Overwrite existing configs')
    args = parser.parse_args()

    identity_file = find_identity_file()

    config = ''    
    all_vms = {}
    for ssh_path in args.ssh_paths:
        parent = None
        for vm_name in ssh_path.split(','):
            vm = all_vms.get(vm_name)
            if vm:
                assert parent == vm.parent, '{}: parent: {}, expected: {}'.format(
                        vm_name,
                        parent.name if parent else 'None',
                        vm.parent.name if vm.parent else 'None')
            else:
                vm = VM(vm_name, parent)
                all_vms[vm_name] = vm
                config += gen_vm_config(vm, identity_file)
            parent = vm

    ssh_config_path = os.path.join('.ssh', 'config')
    ssh_config_file = find_ssh_config_file(ssh_config_path)

    if not ssh_config_file:
        write_config(ssh_config_path, config)
        return

    with open(ssh_config_file, 'r') as f:
        existing_config = f.read()

    if not existing_config.strip():
        write_config(ssh_config_file, config)
    elif existing_config.strip() == config.strip():
        print('Config unchanged')
    elif args.overwrite:
        write_config(ssh_config_file, config)
    else:
        print('Attempting to write different config without allowing overwrite')
        print('Existing config:\n\n{}\n'.format(existing_config.strip()))
        print('New config:\n\n{}\n'.format(config.strip()))


if __name__ == '__main__':
    main()
