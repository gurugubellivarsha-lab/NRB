#!/bin/bash
set -e
cd "$(dirname "$0")"
apt-get update
apt-get install -y python3 python3-pip python3-venv docker.io docker-compose-plugin socat
systemctl enable --now docker
python3 -m venv venv
source venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
chmod +x start.sh nrb-tool.sh
python3 -m py_compile nrb.py docker_backend.py api.py
python3 - <<'PY'
import shutil
print('Docker executable:', shutil.which('docker') or 'NOT FOUND')
PY
echo "NRB Panel V2 is ready."
echo "Docker runtime: enabled"
echo "Start with: ./start.sh"
