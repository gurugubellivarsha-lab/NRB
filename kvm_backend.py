#!/usr/bin/env python3
"""Experimental native KVM backend utilities for NRB Panel.

This module intentionally uses libvirt/virsh rather than Docker or LXD.
It is a worker-side foundation; the existing panel's Docker-specific command
contract must be migrated before this can replace docker_backend.py safely.
"""
from __future__ import annotations
import os, re, shutil, subprocess
from pathlib import Path

class KVMUnavailable(RuntimeError): pass

class KVMRuntime:
    IMAGE_DIR = Path(os.getenv('NRB_KVM_IMAGE_DIR', '/var/lib/libvirt/images/nrb'))
    NETWORK = os.getenv('NRB_KVM_NETWORK', 'default')

    @staticmethod
    def _run(args, timeout=120, check=True):
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        if check and p.returncode:
            raise RuntimeError((p.stderr or p.stdout).strip() or f"Command failed: {args[0]}")
        return p.stdout.strip()

    @classmethod
    def check_host(cls):
        missing = [x for x in ('virsh', 'virt-install', 'qemu-img') if not shutil.which(x)]
        if missing: raise KVMUnavailable('Missing host tools: ' + ', '.join(missing))
        if not Path('/dev/kvm').exists():
            raise KVMUnavailable('/dev/kvm is missing; host virtualization is unavailable or not exposed')
        return {'virsh': shutil.which('virsh'), 'kvm': '/dev/kvm', 'network': cls.NETWORK}

    @classmethod
    def create(cls, name, image=None, ram_mb=1024, cpu=1, disk_gb=10, **kwargs):
        """Create a VM from a local cloud image; image must be supplied by admin."""
        cls.check_host()
        if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}', name):
            raise ValueError('Invalid VM name')
        if cls._run(['virsh','dominfo',name], check=False):
            raise RuntimeError(f'VM {name} already exists')
        if not image:
            raise ValueError('Provide a trusted local cloud image path as image=...')
        source = Path(image).resolve()
        if not source.is_file(): raise FileNotFoundError(f'Cloud image not found: {source}')
        ram_mb, cpu, disk_gb = int(ram_mb or 1024), int(float(cpu or 1)), int(disk_gb or 10)
        if ram_mb < 256 or cpu < 1 or disk_gb < 2: raise ValueError('Resource values are too small')
        cls.IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        disk = cls.IMAGE_DIR / f'{name}.qcow2'
        cls._run(['qemu-img','create','-f','qcow2','-F','qcow2','-b',str(source),str(disk),f'{disk_gb}G'], timeout=120)
        try:
            cls._run(['virt-install','--name',name,'--memory',str(ram_mb),'--vcpus',str(cpu),
                      '--disk',f'path={disk},format=qcow2,bus=virtio','--import','--os-variant','generic',
                      '--network',f'network={cls.NETWORK},model=virtio','--graphics','none','--noautoconsole',
                      '--console','pty,target_type=serial'], timeout=300)
        except Exception:
            disk.unlink(missing_ok=True)
            raise
        return {'name': name, 'disk': str(disk), 'status': cls._run(['virsh','domstate',name])}

    @classmethod
    def action(cls, name, action):
        cls.check_host()
        commands = {'start':'start','stop':'shutdown','destroy':'destroy','restart':'reboot','delete':'undefine'}
        if action not in commands: raise ValueError('Unsupported action')
        if action == 'delete':
            cls._run(['virsh','undefine',name,'--nvram'], check=False)
            (cls.IMAGE_DIR / f'{name}.qcow2').unlink(missing_ok=True)
            return True
        cls._run(['virsh',commands[action],name], timeout=120)
        return True

    @classmethod
    def info(cls, name):
        cls.check_host()
        return cls._run(['virsh','dominfo',name])

    @classmethod
    def list_vms(cls):
        cls.check_host()
        return cls._run(['virsh','list','--all','--name']).splitlines()

if __name__ == '__main__':
    import argparse, json
    p=argparse.ArgumentParser(description='NRB native KVM worker utility')
    sub=p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('check')
    sub.add_parser('list')
    for act in ('start','stop','restart','destroy','delete','info'):
        q=sub.add_parser(act); q.add_argument('name')
    c=sub.add_parser('create'); c.add_argument('name'); c.add_argument('--image',required=True); c.add_argument('--ram-mb',type=int,default=1024); c.add_argument('--cpu',type=int,default=1); c.add_argument('--disk-gb',type=int,default=10)
    a=p.parse_args()
    if a.cmd=='check': out=KVMRuntime.check_host()
    elif a.cmd=='list': out=KVMRuntime.list_vms()
    elif a.cmd=='create': out=KVMRuntime.create(a.name,a.image,a.ram_mb,a.cpu,a.disk_gb)
    elif a.cmd=='info': out=KVMRuntime.info(a.name)
    else: out=KVMRuntime.action(a.name,a.cmd); out={'success':bool(out)}
    print(json.dumps(out,indent=2) if not isinstance(out,str) else out)
