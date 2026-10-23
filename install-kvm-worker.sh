#!/usr/bin/env bash
set -euo pipefail
# Run only on a Linux host you administer. This installs a native KVM worker,
# not inside Railway or an unprivileged container.
if [[ $EUID -ne 0 ]]; then echo 'Run with sudo/root.' >&2; exit 1; fi
. /etc/os-release
case "${ID:-}" in ubuntu|debian) ;; *) echo 'Supported targets: Ubuntu/Debian.' >&2; exit 1;; esac
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virtinst dnsmasq-base python3
systemctl enable --now libvirtd || systemctl enable --now virtqemud
if [[ ! -e /dev/kvm ]]; then echo 'WARNING: /dev/kvm is missing; nested virtualization may not be exposed.' >&2; fi
virsh net-list --all
printf '\nKVM worker packages installed. Check the default libvirt network and /dev/kvm before creating VMs.\n'
printf 'Do not expose the libvirt socket or virsh API publicly. Use a private authenticated channel such as Tailscale.\n'
