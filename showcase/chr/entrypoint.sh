#!/bin/sh
# Boots the CHR VM and runs the traffic simulator beside it.
set -e

# Software emulation works everywhere (Windows/macOS Docker Desktop); KVM is
# only used if /dev/kvm was passed into the container on a Linux host.
ACCEL="-accel tcg"
[ -w /dev/kvm ] && ACCEL="-accel kvm -cpu host"

# The simulator restarts itself if it ever crashes; QEMU is the main process,
# so the container stops (and Docker restarts it) only if the router dies.
( while true; do python3 -u /opt/simulator.py; sleep 2; done ) &

# User-mode networking: the router reaches the compose network through QEMU's
# NAT, and the forwarded ports below let Xiguard and the browser reach it.
#   8728 RouterOS API · 80 WebFig · 8291 Winbox · 22 SSH
exec qemu-system-x86_64 -nographic -m 256 -smp 2 $ACCEL \
  -drive file=/chr/chr.img,format=raw,if=virtio \
  -netdev user,id=n0,hostfwd=tcp::8728-:8728,hostfwd=tcp::80-:80,hostfwd=tcp::8291-:8291,hostfwd=tcp::22-:22 \
  -device virtio-net-pci,netdev=n0,romfile=
