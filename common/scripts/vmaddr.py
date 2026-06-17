#!/usr/bin/env python3

import argparse
import sys
import zlib


def vm_name_to_mac(vm_name):
    """
    Converts a VM name to a MAC address based on its CRC32 hash.

    This generates a consistent MAC address for a given VM name.
    Uses the "52:54" prefix, common for QEMU virtual machines.
    """

    # Calculate the CRC32 checksum of the VM name (encoded as UTF-8 bytes)
    crc32_int = zlib.crc32(vm_name.encode("utf-8"))

    # Convert the CRC32 integer to an 8-character hexadecimal string
    crc32_hex = hex(crc32_int)[2:]  # Remove the "0x" prefix
    crc32_hex = crc32_hex[-8:]  # Take the last 8 hex digits


    # Format the MAC address string
    mac_address = ":".join([
        "52:54",
        crc32_hex[0:2],
        crc32_hex[2:4],
        crc32_hex[4:6],
        crc32_hex[6:8],
    ])

    return mac_address


def mac_to_ipv6_local(mac):
    """
    Converts a MAC address to an IPv6 link-local address using the EUI-64 format.

    Args:
        mac (str): The MAC address in the format "XX:XX:XX:XX:XX:XX".

    Returns:
        str: The IPv6 link-local address.
    """

    # 1. Split the MAC address into individual byte strings
    mac_bytes = mac.split(":")

    # 2. Flip the Universal/Local bit (7th bit) of the first byte
    first_byte_int = int(mac_bytes[0], 16)  # Convert hex string to integer
    flipped_first_byte_int = first_byte_int ^ 0x02  # XOR with 0x02 to flip the bit
    mac_bytes[0] = "%x" % flipped_first_byte_int  # Convert back to hex string

    # 3. Insert "ff:fe" into the middle of the MAC address to create the EUI-64
    eui64 = mac_bytes[:3] + ["ff", "fe"] + mac_bytes[3:]

    # 4. Construct the IPv6 link-local address (fe80::EUI-64)
    ipv6_link_local = "fe80::"

    # 5. Concatenate the EUI-64 bytes, forming the interface identifier
    for i in range(0, len(eui64), 2):
        ipv6_link_local += eui64[i] + eui64[i + 1]
        if i < len(eui64) - 2:
            ipv6_link_local += ":"

    return ipv6_link_local


def vm_name_to_ipv6_local(vm_name):
    return mac_to_ipv6_local(vm_name_to_mac(vm_name))

def main():
    parser = argparse.ArgumentParser(prog='vmaddr.py',
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('name', type=str, help='VM name')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-m', '--mac', action="store_true", help="Print MAC address")
    group.add_argument('-i', '--ip', action="store_true", help="Print IPv6 link-local address")
    args = parser.parse_args()

    mac = vm_name_to_mac(args.name)
    ipv6 = mac_to_ipv6_local(mac)

    if args.mac:
        print(mac)
    elif args.ip:
        print(ipv6)
    else:
        print(f"mac: {mac}\nipv6 local link addr: {ipv6}")


if __name__ == '__main__':
    main()

