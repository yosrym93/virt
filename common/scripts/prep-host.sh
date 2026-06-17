#!/bin/sh

set -e
set -x

SCRIPTS_DIR="$(dirname $0)"
PREP_COMMON="${SCRIPTS_DIR}/prep-common.sh"

COMMON_DIR="$(dirname ${SCRIPTS_DIR})"
QEMU="${COMMON_DIR}/qemu/qemu-system-x86_64"

TOYBOX="${COMMON_DIR}/bin/toybox"
TOYBOX_BIN_DIR="/data/toybox-bin"

TARGET_BIN="/usr/local/bin"
BASHRC="${HOME}/.bashrc"

TOYBOX_UTILS=( timeout base64 )

function write_bashrc()
{
	echo >> $BASHRC
	echo $1 >> $BASHRC
	source $BASHRC
}

if ! which python3 > /dev/null 2>&1; then
    echo "Creating python3 symlink..."
    sudo ln -sf /bin/kpython3 "${TARGET_BIN}/python3"
fi

# 2. Link all scripts from SCRIPTS_DIR into /usr/local/bin
# This replaces "Adding scripts directory to PATH"
echo "Linking scripts to ${TARGET_BIN}"
for script in "${SCRIPTS_DIR}"/*; do
    if [ -x "$script" ] && [ -f "$script" ]; then
        sudo ln -sf "$script" "${TARGET_BIN}/$(basename "$script")"
    fi
done

# 3. Link Toybox utils
echo "Creating symlinks for toybox utils"
for cmd in "${TOYBOX_UTILS[@]}"; do
    sudo ln -sf "${TOYBOX}" "${TARGET_BIN}/$cmd"
done

# 4. Handle QEMU
# Since QEMU is an environment variable, not just a binary,
# we link the binary so it's callable, but for the variable
# itself, you'll still need to export it or reference the link.
sudo ln -sf "${QEMU}" "${TARGET_BIN}/qemu-system-x86_64"

: '
# Add scripts directory to $PATH in $BASHRC
if ! egrep -q "PATH.*${SCRIPTS_DIR}" $BASHRC; then
	echo "Adding scripts directory to PATH"
        write_bashrc "export PATH=\"${SCRIPTS_DIR}:\$PATH\""
fi

# Add some utils from toybox to $PATH in $BASHRC
if ! egrep -q "PATH.*${TOYBOX_BIN_DIR}" $BASHRC; then
	mkdir -p ${TOYBOX_BIN_DIR}
	echo "Creating symlinks for toybox utils"
	for cmd in ${TOYBOX_UTILS[@]}; do
		ln -sf ${TOYBOX} "${TOYBOX_BIN_DIR}/$cmd"
	done
	echo "Adding toybox utils to PATH"
        write_bashrc "export PATH=\"${TOYBOX_BIN_DIR}:\$PATH\""
fi

# Add QEMU to ~/.bashrc for KUTs
if ! egrep -q "QEMU.*${QEMU}" ~/.bashrc; then
	write_bashrc "export QEMU=\"${QEMU}\""
fi
'

# Generate SSH configs for L1 and L2
$SCRIPTS_DIR/gen_ssh_config.py l1,l2

$PREP_COMMON
