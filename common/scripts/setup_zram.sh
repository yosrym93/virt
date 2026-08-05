#!/bin/bash

set -e

SIZE="2G"
DEV="/dev/zram0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--size)   SIZE="${2:?Missing value for size}"; shift 2 ;;
    -d|--device) DEV="${2:?Missing value for device}"; shift 2 ;;
    -h|--help)   echo "Usage: sudo $0 [-s size] [-d device]"; exit 0 ;;
    *)           echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

dev_name=$(basename "$DEV")

echo "Setting up $DEV ($SIZE)..."
modprobe zram

[[ -b "$DEV" ]] && echo 1 > "/sys/block/$dev_name/reset" 2>/dev/null || true
echo "$SIZE" > "/sys/block/$dev_name/disksize"
mkswap "$DEV" >/dev/null
swapon "$DEV"
