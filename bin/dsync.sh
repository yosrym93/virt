#!/bin/sh

set -e

common=true
prep=true
image=false
kernel=false

while getopts "ick" opt; do
	case "$opt" in
		# Only image
		i)
			image=true
			common=false
			prep=false
			;;
		# Only kernels
		k)
			kernel=true
			common=false
			prep=false
			;;
		\?)
			echo "Invalid option: -$OPTARG" >&2
			exit 1
			;;
	esac
done

shift $((OPTIND - 1)) # Shift past the processed options

if [ $# -eq 0 ]; then
	echo "Usage: $0 [-i] <machine>" >&2
	exit 1
fi

USER=$(whoami)
MACHINE=$1
LOCAL_VIRT_DIR="$HOME/virt"
LOCAL_COMMON_DIR="$LOCAL_VIRT_DIR/common"
LOCAL_KERNEL_DIR="$HOME/builds/kernel"
LOCAL_L1_IMG_PATH="$LOCAL_VIRT_DIR/imgs/ubuntu-24.04-l1.img"
REMOTE_VIRT_DIR="/data/$USER/virt"
REMOTE_COMMON_DIR="$REMOTE_VIRT_DIR/common"
REMOTE_KERNEL_DIR="$REMOTE_COMMON_DIR/kernel"
REMOTE_IMGS_DIR="$REMOTE_VIRT_DIR/imgs"

function my_rsync()
{
	rsync -az --progress "$@"
}

# Create the remote directories if they do not exist
ssh root@$MACHINE mkdir -p $REMOTE_KERNEL_DIR

# Copy the common directory
if $common; then
	my_rsync "$LOCAL_COMMON_DIR/" "root@$MACHINE:$REMOTE_COMMON_DIR/"
fi

# Copy the L1 image
if $image; then
	my_rsync "$LOCAL_L1_IMG_PATH" "root@$MACHINE:$REMOTE_IMGS_DIR/"
fi

# Copy the built kernels' binaries and modules
if $kernel; then
	for dir in $(find $LOCAL_KERNEL_DIR -mindepth 1 -maxdepth 1 -type d); do
		name=$(basename $dir)
		bin=$(find $dir -name bzImage -type f)
		modules=$(find $dir -maxdepth 2 -path "*/modules/lib" -type d)
		selftests=$(find $dir -maxdepth 1 -path "*/selftests" -type d)
		dst_dir="$REMOTE_KERNEL_DIR/$name"

		echo $name
		ssh root@$MACHINE mkdir -p $dst_dir
		my_rsync --delete $bin $modules $selftests "root@$MACHINE:$dst_dir/"
	done
fi

# Run prep-host.sh
if $prep; then
	ssh root@$MACHINE "$REMOTE_VIRT_DIR/common/bin/prep-host.sh"
fi
