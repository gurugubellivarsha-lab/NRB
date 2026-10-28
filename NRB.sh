
#!/usr/bin/env bash
set -Eeuo pipefail

# NRB Panel V3 - One-command installer
# Ubuntu / Debian
# Port: 3000

REPO="https://github.com/gurugubellivarsha-lab/NRB.git"
APP_DIR="/opt/nrb-panel"
PORT="3000"

if [[ $EUID -ne 0 ]]; then
    echo "Run this installer as root: sudo bash install_nrb.sh"
    exit 1
fi

echo "======================================"
echo "       NRB Panel Installation"
echo "======================================"

export DEBIAN_FRONTEND=noninteractive

echo "[1/7] Installing system packages..."
apt-get update
apt-get install -y \
    git curl ca-certificates gnupg \
    python3 python3-pip python3-venv \
    build-essential pkg-config

echo "[2/7] Installing Cloudflare Tunnel..."
install -d -m 0755 /usr/share/keyrings

curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    -o /usr/share/keyrings/cloudflare-main.gpg

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" \
    > /etc/apt/sources.list.d/cloudflared.list

apt-get update
apt-get install -y cloudflared

cloudflared --version

echo "[3/7] Cloning NRB Panel..."
if [[ -d "$APP_DIR/.git" ]]; then
    echo "Existing Git repository found."
    echo "Keeping existing files; no automatic reset or overwrite."
else
    if [[ -e "$APP_DIR" ]]; then
        echo "ERROR: $APP_DIR exists but is not a Git repository."
        echo "Back up or move that directory before continuing."
        exit 1
    fi
    git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"

echo "[4/7] Creating Python virtual environment..."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

if [[ -f requirements.txt ]]; then
    echo "Installing requirements.txt..."
    pip install -r requirements.txt
else
    echo "ERROR: requirements.txt not found."
    echo "Check your repository's dependency instructions."
    exit 1
fi

if [[ ! -f nrb.py ]]; then
    echo "ERROR: nrb.py not found in the repository root."
    echo "Check the actual startup filename before continuing."
    exit 1
fi

echo "[5/7] Configuring panel port..."
echo "PORT=$PORT"
echo "Note: the application must support port 3000."
echo "Set its port using the configuration expected by the project."

echo "[6/7] Cloudflare Tunnel token"
echo "Create a remotely managed tunnel in the Cloudflare dashboard."
echo "Copy its tunnel token (not an API token)."
echo "See: https://developers.cloudflare.com/tunnel/get-started/"
echo

read -r -s -p "Paste Cloudflare Tunnel token: " CF_TOKEN
echo
if [[ -z "$CF_TOKEN" ]]; then
    echo "ERROR: No token entered."
    exit 1
fi

echo "[7/7] Starting NRB Panel and Cloudflare Tunnel..."
# Keep the token out of shell history and avoid writing it to a file.
# The tunnel token is supplied to cloudflared via its environment.
(
    export TUNNEL_TOKEN="$CF_TOKEN"
    unset CF_TOKEN
    exec cloudflared tunnel run --token "$TUNNEL_TOKEN"
) &
TUNNEL_PID=$!
unset CF_TOKEN

cleanup() {
    kill "$TUNNEL_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2
if ! kill -0 "$TUNNEL_PID" 2>/dev/null; then
    echo "ERROR: Cloudflare Tunnel failed to start."
    exit 1
fi

cd "$APP_DIR"
source .venv/bin/activate
echo "Starting NRB Panel on port $PORT..."
python3 nrb.py
