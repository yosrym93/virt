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
