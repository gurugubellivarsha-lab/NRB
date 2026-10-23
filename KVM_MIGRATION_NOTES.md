# NRB Panel — native KVM migration notes

This package adds an experimental host-side KVM utility without changing the existing panel's Docker contract. The current `nrb.py` imports `DockerRuntime` and its provisioning, console, port-forwarding, and node-agent routes issue Docker-specific commands. Replacing that import alone is unsafe and will break parts of VPS creation.

## Worker prerequisites

- A supported Ubuntu/Debian host with `/dev/kvm` exposed and permissions configured.
- `qemu-kvm`, `qemu-utils`, `libvirt`, `virt-install`, and a working libvirt network.
- A trusted local cloud image (QCOW2) for the chosen guest OS.
- Private connectivity to the worker (Tailscale is suitable); never expose the libvirt socket or an unauthenticated command API to the internet.

## Install/check

Run `sudo bash install-kvm-worker.sh` on the KVM host, then:

```bash
sudo python3 kvm_backend.py check
sudo python3 kvm_backend.py list
```

Create a VM from an administrator-provided local cloud image:

```bash
sudo python3 kvm_backend.py create test-vm --image /var/lib/libvirt/images/ubuntu-cloudimg.qcow2 --ram-mb 1024 --cpu 1 --disk-gb 10
```

The image should be a suitable cloud image. This utility does not configure guest credentials or SSH by itself; use cloud-init and SSH keys before making a VM available to a customer.

## Important limitations

- This is a worker-side foundation, not yet a drop-in replacement for `docker_backend.py`.
- Full panel integration requires migrating the existing Docker command grammar, node API, console, networking/port forwarding, resource edits, and guest initialization to libvirt/cloud-init. Those paths must be tested together before production use.
- KVM requires a persistent host and suitable privileges. Railway application containers are not a KVM host. Tailscale supplies private connectivity, not virtualization capability or uptime guarantees.
