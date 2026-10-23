#!/usr/bin/env python3
"""Docker runtime for NRB VPS containers.
No Docker runtime dependency is required.
"""
import asyncio, os, re, shlex, socket, subprocess
from pathlib import Path

class DockerRuntime:
    @staticmethod
    def _image(value: str) -> str:
        v=(value or 'ubuntu:22.04').strip()
        mapping={
            'images:debian/10':'debian:10', 'images:debian/11':'debian:11',
            'images:debian/12':'debian:12', 'images:debian/13':'debian:13',
            'ubuntu:20.04':'ubuntu:20.04', 'ubuntu:22.04':'ubuntu:22.04',
            'ubuntu:24.04':'ubuntu:24.04',
        }
        return mapping.get(v, v if ':' in v else 'ubuntu:22.04')

    @staticmethod
    def _run_sync(args, timeout=120, check=True):
        p=subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if check and p.returncode:
            raise RuntimeError(p.stderr.strip() or f"Docker command failed ({p.returncode})")
        return p.stdout.strip()

    @staticmethod
    def _exists(name):
        return subprocess.run(['docker','inspect',name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode==0

    @staticmethod
    def _alloc_ssh_port():
        for port in range(22000,23000):
            with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s:
                try: s.bind(('0.0.0.0',port))
                except OSError: continue
            # Docker may already own it; docker ps check is authoritative.
            out=subprocess.run(['docker','ps','--format','{{.Ports}}'],capture_output=True,text=True).stdout
            if f':{port}->' not in out and f'0.0.0.0:{port}' not in out:
                return port
        raise RuntimeError('No free Docker SSH host port available in 22000-22999')

    @classmethod
    def create(cls,name,image,ram_mb=None,cpu=None,disk_gb=None):
        if cls._exists(name):
            raise RuntimeError(f'Docker container {name} already exists')
        image=cls._image(image)
        cls._run_sync(['docker','pull',image],timeout=600)
        ssh_port=cls._alloc_ssh_port()
        args=['docker','run','-d','--name',name,'--hostname',name,'--restart','unless-stopped',
              '--privileged','--cap-add=NET_ADMIN','--cap-add=SYS_MODULE']
        # Tailscale inside the VPS needs the host TUN device. Add it when the
        # Docker host exposes it; otherwise the VPS can still be created and
        # SSH remains available.
        if os.path.exists('/dev/net/tun'):
            args += ['--device','/dev/net/tun:/dev/net/tun']
        args += ['-p',f'0.0.0.0:{ssh_port}:22']
        if ram_mb:
            # Docker requires memory-swap to be >= memory. Keep both equal so
            # the requested RAM is deterministic and Docker never rejects the run.
            mem=f'{int(ram_mb)}m'
            args += ['--memory',mem,'--memory-swap',mem]
        if cpu:
            args += ['--cpus',str(cpu)]
        # disk_gb is intentionally not passed as --storage-opt here. Docker
        # storage quotas depend on the host storage driver and can make VPS
        # creation fail on ordinary overlay2 hosts. NRB records the requested
        # disk size in the panel instead of turning it into a daemon error.
        args += [image,'sleep','infinity']
        cls._run_sync(args,timeout=120)
        return ssh_port

    @classmethod
    def update(cls,name,privileged=False,ram_mb=None,cpu=None):
        args=['docker','update']
        if privileged:
            # Privileged cannot be changed by docker update; container is created privileged.
            pass
        if ram_mb:
            # Keep memory-swap equal to memory to avoid Docker's daemon error
            # when a memory limit is changed on an existing container.
            mem=f'{int(ram_mb)}m'
            args += ['--memory',mem,'--memory-swap',mem]
        if cpu: args += ['--cpus',str(cpu)]
        if len(args)>2: cls._run_sync(args+[name])

    @classmethod
    def _container_ip(cls, name):
        return cls._run_sync(['docker','inspect','-f','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',name])

    @classmethod
    def _proxy_add(cls, name, command):
        parts=shlex.split(command)
        # config device add <name> tcp_proxy_<host> proxy listen=tcp:0.0.0.0:<host> connect=tcp:127.0.0.1:<vps>
        if len(parts) < 7: return True
        device=parts[3]
        host=re.search(r'listen=(tcp|udp):0\.0\.0\.0:(\d+)', command)
        target=re.search(r'connect=(?:tcp|udp):127\.0\.0\.1:(\d+)', command)
        if not host or not target: return True
        proto,host_port=host.group(1),int(host.group(2)); vps_port=int(target.group(1))
        ip=cls._container_ip(name)
        pidfile=Path('/run')/f'nrb-socat-{name}-{proto}-{host_port}.pid'
        if pidfile.exists():
            try: os.kill(int(pidfile.read_text().strip()),15)
            except Exception: pass
            pidfile.unlink(missing_ok=True)
        listen=f'{proto.upper()}-LISTEN:{host_port},reuseaddr,fork'
        target_arg=f'{proto.upper()}:{ip}:{vps_port}'
        proc=subprocess.Popen(['socat',listen,target_arg],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        pidfile.write_text(str(proc.pid))
        return True

    @classmethod
    def _proxy_remove(cls, name, command):
        parts=shlex.split(command)
        m=re.search(r'(tcp|udp)_proxy_(\d+)', command)
        if not m: return True
        proto,port=m.group(1),m.group(2)
        pidfile=Path('/run')/f'nrb-socat-{name}-{proto}-{port}.pid'
        if pidfile.exists():
            try: os.kill(int(pidfile.read_text().strip()),15)
            except Exception: pass
            pidfile.unlink(missing_ok=True)
        return True

    @classmethod
    async def run(cls,name,command,timeout=120):
        def work():
            c=command.strip()
            # Lifecycle
            if c.startswith('init '):
                parts=shlex.split(c)
                image=parts[1] if len(parts)>1 else 'ubuntu:22.04'
                cname=parts[2] if len(parts)>2 else name
                ram_mb=None; cpu=None; disk_gb=None
                i=3
                while i < len(parts):
                    token=parts[i]
                    if token in ('-m','--memory') and i+1 < len(parts):
                        raw=re.sub(r'[^0-9.]','',parts[i+1]); ram_mb=int(float(raw)) if raw else None
                        # Accept GB/G forms as well as MB.
                        if parts[i+1].lower().endswith(('gb','g')): ram_mb *= 1024
                        i += 2; continue
                    if token in ('-c','--cpus') and i+1 < len(parts):
                        cpu=float(parts[i+1]); i += 2; continue
                    if token in ('-d','--disk') and i+1 < len(parts):
                        raw=re.sub(r'[^0-9.]','',parts[i+1]); disk_gb=int(float(raw)) if raw else None
                        i += 2; continue
                    i += 1
                return str(cls.create(cname,image,ram_mb=ram_mb,cpu=cpu,disk_gb=disk_gb))
            if c.startswith('start '): cls._run_sync(['docker','start',name]); return True
            if c.startswith('stop '): cls._run_sync(['docker','stop','-t','0',name]); return True
            if c.startswith('restart '): cls._run_sync(['docker','restart',name]); return True
            if c.startswith('freeze '): cls._run_sync(['docker','pause',name]); return True
            if c.startswith('unfreeze '): cls._run_sync(['docker','unpause',name]); return True
            if c.startswith('delete '): cls._run_sync(['docker','rm','-f',name]); return True
            if c.startswith('info '):
                status=cls._run_sync(['docker','inspect','-f','{{.State.Status}}',name])
                ip=cls._run_sync(['docker','inspect','-f','{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',name])
                return f'Status: {status.title()}\nIP: {ip}\n'
            # Docker resource config commands
            if c.startswith('config set '):
                parts=shlex.split(c)
                # config set <name> limits.memory 2048MB
                if len(parts)>=5 and parts[3]=='limits.memory':
                    mb=re.sub(r'[^0-9.]','',parts[4]); mem=f'{int(float(mb))}m'; cls._run_sync(['docker','update','--memory',mem,'--memory-swap',mem,name]); return True
                if len(parts)>=5 and parts[3]=='limits.cpu':
                    cls._run_sync(['docker','update','--cpus',parts[4],name]); return True
                return True
            if c.startswith('config device set '):
                # Docker's writable layer size is storage-driver dependent; don't fail VPS creation.
                return True
            if c.startswith('config device add '):
                return cls._proxy_add(name, c)
            if c.startswith('config device remove '): return cls._proxy_remove(name, c)
            if c.startswith('config '): return True
            if c.startswith('exec '):
                # exec <container> -- <payload>
                rest=c[len('exec '):]
                if ' -- ' in rest:
                    cname,payload=rest.split(' -- ',1)
                    cname=cname.strip()
                    payload=payload.lstrip()
                    # Older builds wrapped the complete script with shlex.quote().
                    # If that format is received, unwrap exactly one outer shell token
                    # so Docker executes the script itself instead of trying to execute
                    # the quoted text as a command name. Plain commands remain untouched.
                    if len(payload) >= 2 and payload[0] in ("'", '"') and payload[-1] == payload[0]:
                        try:
                            decoded=shlex.split(payload, posix=True)
                            if len(decoded) == 1:
                                payload=decoded[0]
                        except ValueError:
                            pass
                else:
                    parts=shlex.split(rest); cname=parts[0]; payload=' '.join(parts[1:])
                return cls._run_sync(['docker','exec',cname,'sh','-lc',payload],timeout=timeout)
            return cls._run_sync(['docker']+shlex.split(c),timeout=timeout)
        return await asyncio.to_thread(work)

    @staticmethod
    def translate_command(name, command):
        c=command.strip()
        if c.startswith('start '): return f'start {name}'
        if c.startswith('stop '): return f'stop {name}'
        if c.startswith('restart '): return f'restart {name}'
        if c.startswith('freeze '): return f'pause {name}'
        if c.startswith('unfreeze '): return f'unpause {name}'
        if c.startswith('delete '): return f'rm -f {name}'
        if c.startswith('exec '):
            rest=c[len('exec '):]
            if ' -- ' in rest:
                cname,payload=rest.split(' -- ',1)
                return f"exec {shlex.quote(cname.strip())} sh -lc {shlex.quote(payload.lstrip())}"
            parts=shlex.split(rest)
            if len(parts) >= 2:
                return f"exec {shlex.quote(parts[0])} sh -lc {shlex.quote(' '.join(parts[1:]))}"
            return f'exec {rest}'
        if c.startswith('config set '):
            parts=shlex.split(c)
            if len(parts)>=5 and parts[3]=='limits.memory':
                mem=re.sub(r'[^0-9.]','',parts[4]); mem=f'{int(float(mem))}MB'; return f"update --memory {mem} --memory-swap {mem} {name}"
            if len(parts)>=5 and parts[3]=='limits.cpu':
                return f"update --cpus {parts[4]} {name}"
        if c.startswith('info '): return f"inspect {name}"
        return c
