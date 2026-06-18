#!/bin/sh
ip link set dev "$1" up 2>/dev/null || true
