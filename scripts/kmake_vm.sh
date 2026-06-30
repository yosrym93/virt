#!/bin/sh
# Build a kernel out-of-tree with make, mainly for running in a VM.

set -e

BUILD_DIR="${BUILD_DIR:=$HOME/builds/kernel/$(basename $(pwd))}"
KERNEL_DIR="$BUILD_DIR/kernel"
MODULES_DIR="$BUILD_DIR/modules"
SELFTESTS_DIR="$BUILD_DIR/selftests"

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
REPO_DIR=$(dirname "$SCRIPT_DIR")
VM_CONFIG="${VM_CONFIG:=$(find "$REPO_DIR" -name "vm.config" | head -n 1)}"
ALL_CONFIG="${ALL_CONFIG:=$(find "$REPO_DIR" -name "all.config" | head -n 1)}"

mkdir -p $KERNEL_DIR

selftests=false
while getopts "t" opt; do
	case "$opt" in
		t)
			selftests=true
			;;
		\?)
			echo "Invalid option: -$OPTARG" >&2
			exit 1
			;;
	esac
done

shift $((OPTIND - 1)) # Shift past the processed options

config=$1
if [[ $config == "clean" ]]; then
	make clean O=$KERNEL_DIR
	rm -rf $MODULES_DIR
	rm -rf $SELFTESTS_DIR
	exit
fi

if [[ -z $config && -f "$KERNEL_DIR/.config" ]]; then
	echo "Reusing existing config at $KERNEL_DIR/.config"
else
	if [[ $config == "all" ]]; then
		config_file=$ALL_CONFIG
	elif [[ -n $config ]]; then
		config_file=$config
	else
		config_file=$VM_CONFIG
	fi

	echo "Using $config_file"
	cp $config_file "$KERNEL_DIR/.config"
	make olddefconfig LLVM=1 O="$KERNEL_DIR"
fi

echo "Building the kernel"
make -s -j $(nproc) LLVM=1 O=$KERNEL_DIR

echo "Building modules"
rm -rf $MODULES_DIR/*
make -s -j $(nproc) LLVM=1 O=$KERNEL_DIR INSTALL_MOD_PATH=$MODULES_DIR modules_install

if $selftests; then
	echo "Building selftests"
	make -s -j $(nproc) LLVM=1 O=$KERNEL_DIR headers_install
	make -s -j $(nproc) -C tools/testing/selftests TARGETS=kvm \
		EXTRA_CFLAGS="-static -gdwarf-4" LLVM=1 \
		O=$KERNEL_DIR \
		KHDR_INCLUDES="-isystem $KERNEL_DIR/usr/include" \
		INSTALL_HDR_PATH="$KERNEL_DIR/usr" \
		INSTALL_PATH=$SELFTESTS_DIR \
		install
fi

