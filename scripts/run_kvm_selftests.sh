#!/bin/bash

OUT="out-$(date +%s)"
DIR="${DIR:=selftests}"

# Tests to skip entirely
declare -A SKIP_TESTS=(
	["nx_huge_pages_test"]=1
	["hardware_disable_test"]=1
	["config"]=1
	["settings"]=1
)

# Tests that need to be run in nested mode (with "-n") as well
declare -A NESTED_TESTS=(
	["dirty_log_perf_test"]=1
	["stress_save_restore_pf_test"]=1
)

function run_test() {
	test=$1
	echo $test

	$DIR/$test
	exit_code=$?
	if [[ exit_code -eq 0 ]]; then
		echo "$test PASSED"
	elif [[ exit_code -eq 4 ]]; then
		echo "$test SKIPPED"
	else
		echo "$test FAILED"
	fi

	echo
	echo "----------------"
	echo
}

function find_memory_cgroup_root() {
	# Try to find cgroup v2 mount point
	local v2_mount=$(awk '$3 == "cgroup2" {print $2; exit}' /proc/mounts)
	if [[ -n "$v2_mount" ]]; then
		echo "$v2_mount"
		return 0
	fi

	# Try to find cgroup v1 memory mount point
	local v1_memory_mount=$(awk '$3 == "cgroup" && $4 ~ /memory/ {print $2; exit}' /proc/mounts)
	if [[ -n "$v1_memory_mount" ]]; then
		echo "$v1_memory_mount"
		return 0
	fi

	return 1
}

function enter_cgroup_root() {
	local root=$(find_memory_cgroup_root)
	if [[ -z "$root" ]]; then
		echo "Warning: Could not find memory cgroup root" >&2
		return 1
	fi

	echo "Found memory cgroup root at: $root"

	if [[ -f "$root/cgroup.procs" ]]; then
		if echo 0 > "$root/cgroup.procs" 2>/dev/null; then
			echo "Entered cgroup: $root"
			return 0
		fi
	fi

	echo "Failed to enter cgroup: $root (might need root)" >&2
	return 1
}

enter_cgroup_root

(for t in $(ls $DIR); do
	if [[ -v SKIP_TESTS[$t] ]]; then
		continue;
	fi

	run_test $t

	if [[ -v NESTED_TESTS[$t] ]]; then
		run_test "$t -n"
	fi
done) 2>&1 | tee $OUT 

echo "# of passed tests: $(grep -c PASSED $OUT)"
echo "# of failed tests: $(grep -c FAILED $OUT)"
grep FAILED $OUT
