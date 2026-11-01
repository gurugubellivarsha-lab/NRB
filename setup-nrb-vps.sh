
#!/bin/bash
set -e

apt update
apt install -y git python3 python3-venv python3-pip

mkdir -p /opt/nrb
cd /opt/nrb

if [ ! -d .git ]; then
    git clone https://github.com/gurugubellivarsha-lab/NRB.git .
else
    git pull origin main
fi

python3 -m venv venv
./venv/bin/pip install --upgrade pip

if [ -f requirements.txt ]; then
    ./venv/bin/pip install -r requirements.txt
fi

mkdir -p /opt/nrb-data/vps_data
mkdir -p /opt/nrb-data/backups

cat > /etc/systemd/system/nrb.service <<'EOF'
[Unit]
Description=NRB Panel
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/nrb
Environment=PORT=3000
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/nrb/venv/bin/python /opt/nrb/nrb.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nrb
systemctl restart nrb

echo "NRB Panel service installed."
systemctl status nrb --no-pager
