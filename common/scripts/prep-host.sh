#!/bin/sh

set -e
set -x

SCRIPTS_DIR="$(dirname $0)"
PREP_COMMON="${SCRIPTS_DIR}/prep-common.sh"

COMMON_DIR="$(dirname "${SCRIPTS_DIR}")"
TARGET_BIN="/usr/local/bin"

if ! which python3 > /dev/null 2>&1; then
    echo "Creating python3 symlink..."
    sudo ln -sf /bin/kpython3 "${TARGET_BIN}/python3"
fi

$PREP_COMMON

# Symlink QEMU bios files to a path that is checked by QEMU by default.
# This is needed for invocations to QEMU through scripts (e.g. kvm-unit-tests)
# that do not allow specifying a path to the bios files.
mkdir -p "${COMMON_DIR}/share"
ln -sf ../qemu/pc-bios "${COMMON_DIR}/share/qemu"

# Optionally link Toybox applets for host KUT test environments if present
TOYBOX="${TARGET_BIN}/toybox"
if [ -f "${TOYBOX}" ]; then
    TOYBOX_UTILS=( timeout base64 )
    for cmd in "${TOYBOX_UTILS[@]}"; do
        if ! which "$cmd" > /dev/null 2>&1; then
            sudo ln -sf "${TOYBOX}" "${TARGET_BIN}/$cmd"
        fi
    done
fi
