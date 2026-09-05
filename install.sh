#!/usr/bin/env bash
# PawTrack installer — run this from inside a cloned copy of the repo, as
# root, on the Debian/Ubuntu server that will host the app:
#
#   git clone https://github.com/<you>/pet-tracking-meshtastic.git
#   cd pet-tracking-meshtastic
#   sudo ./install.sh
#
# It installs PawTrack as a systemd service under /opt/pawtrack, with an
# nginx reverse proxy in front of it. Camera support (mediamtx) is optional.
# Re-running this script on an existing install updates the code and
# restarts the service without touching your database or .env file.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (sudo ./install.sh)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${PAWTRACK_INSTALL_DIR:-/opt/pawtrack}"
SERVICE_USER="${PAWTRACK_SERVICE_USER:-pawtrack}"
MEDIAMTX_VERSION="v1.20.1"

case "$(uname -m)" in
  x86_64) MEDIAMTX_ARCH="linux_amd64" ;;
  aarch64|arm64) MEDIAMTX_ARCH="linux_arm64v8" ;;
  armv7l) MEDIAMTX_ARCH="linux_armv7" ;;
  *) MEDIAMTX_ARCH="" ;;
esac

echo "==> PawTrack installer"
echo "    install dir: $INSTALL_DIR"

read -rp "Enable the camera viewer / PTZ feature (installs mediamtx)? [Y/n] " WANT_CAMERAS
WANT_CAMERAS="${WANT_CAMERAS:-Y}"

read -rp "Set up an nginx reverse proxy on port 80 now? [Y/n] " WANT_NGINX
WANT_NGINX="${WANT_NGINX:-Y}"

echo "==> installing packages"
apt-get update -qq
PKGS="python3-venv python3-pip rsync curl"
if [[ "$WANT_NGINX" =~ ^[Yy]$ ]]; then PKGS="$PKGS nginx"; fi
apt-get install -y -qq $PKGS

echo "==> creating service user + directories"
id -u "$SERVICE_USER" >/dev/null 2>&1 || useradd -r -m -d "/home/$SERVICE_USER" -s /usr/sbin/nologin "$SERVICE_USER"
mkdir -p "$INSTALL_DIR/data"

echo "==> copying application code"
rsync -a --delete \
  --exclude '.git' --exclude '.venv' --exclude 'data' --exclude '__pycache__' --exclude 'node_modules' \
  "$SCRIPT_DIR/backend" "$INSTALL_DIR/"
rsync -a --delete --exclude '.git' "$SCRIPT_DIR/frontend" "$INSTALL_DIR/"

echo "==> python virtualenv + dependencies"
python3 -m venv "$INSTALL_DIR/backend/.venv"
"$INSTALL_DIR/backend/.venv/bin/pip" install -q --upgrade pip
"$INSTALL_DIR/backend/.venv/bin/pip" install -q -r "$INSTALL_DIR/backend/requirements.txt"

ENV_FILE="$INSTALL_DIR/backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "==> generating secret key"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  cat > "$ENV_FILE" <<EOF
PAWTRACK_SECRET_KEY=$SECRET
EOF
else
  echo "==> keeping existing $ENV_FILE"
fi

if [[ "$WANT_CAMERAS" =~ ^[Yy]$ ]]; then
  if [ -z "$MEDIAMTX_ARCH" ]; then
    echo "!! unrecognized CPU architecture ($(uname -m)) — skipping mediamtx, cameras won't work until you install it manually."
  else
    echo "==> installing mediamtx (RTSP -> HLS for the camera viewer)"
    mkdir -p "$INSTALL_DIR/mediamtx"
    if [ ! -f "$INSTALL_DIR/mediamtx/mediamtx" ]; then
      TMP_TGZ="$(mktemp)"
      curl -sL -o "$TMP_TGZ" \
        "https://github.com/bluenviron/mediamtx/releases/download/${MEDIAMTX_VERSION}/mediamtx_${MEDIAMTX_VERSION}_${MEDIAMTX_ARCH}.tar.gz"
      tar -xzf "$TMP_TGZ" -C "$INSTALL_DIR/mediamtx" mediamtx
      rm -f "$TMP_TGZ"
    fi
    if [ ! -f "$INSTALL_DIR/mediamtx/mediamtx.yml" ]; then
      cp "$SCRIPT_DIR/deploy/mediamtx.yml" "$INSTALL_DIR/mediamtx/mediamtx.yml"
    fi
    chmod +x "$INSTALL_DIR/mediamtx/mediamtx"

    cat > /etc/systemd/system/pawtrack-mediamtx.service <<EOF
[Unit]
Description=mediamtx (RTSP to HLS remuxer for PawTrack cameras)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/mediamtx
ExecStart=$INSTALL_DIR/mediamtx/mediamtx $INSTALL_DIR/mediamtx/mediamtx.yml
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR/mediamtx
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF
    systemctl enable --now pawtrack-mediamtx >/dev/null
    systemctl restart pawtrack-mediamtx
  fi
fi

echo "==> writing systemd service"
cat > /etc/systemd/system/pawtrack.service <<EOF
[Unit]
Description=PawTrack
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/backend
Environment=PAWTRACK_DATA_DIR=$INSTALL_DIR/data
Environment=PAWTRACK_FRONTEND_DIR=$INSTALL_DIR/frontend
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR/data
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
systemctl daemon-reload
systemctl enable --now pawtrack >/dev/null
systemctl restart pawtrack

if [[ "$WANT_NGINX" =~ ^[Yy]$ ]]; then
  echo "==> configuring nginx"
  cp "$SCRIPT_DIR/deploy/nginx-pawtrack.conf" /etc/nginx/sites-available/pawtrack
  ln -sf /etc/nginx/sites-available/pawtrack /etc/nginx/sites-enabled/pawtrack
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl restart nginx
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "==> done!"
if [[ "$WANT_NGINX" =~ ^[Yy]$ ]]; then
  echo "    Open http://${IP:-<this-server-ip>}/ and register the first account — it becomes the admin automatically."
else
  echo "    PawTrack is running on 127.0.0.1:8000 — put your own reverse proxy (nginx, Caddy, Cloudflare Tunnel...) in front of it."
  echo "    See deploy/nginx-pawtrack.conf for a working example config, including the /ws WebSocket upgrade headers it needs."
fi
echo "    Logs: journalctl -u pawtrack -f"
