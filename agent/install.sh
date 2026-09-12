#!/usr/bin/env bash
# Installs the MIT Panel monitoring agent as a systemd service.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/liwyd/mit-panel/main/agent/install.sh \
#     | sudo bash -s -- --url "https://panel.example.com/dashboard" --token "<agent-token>"
#
# Must run as root: the agent needs privilege to reboot the machine, and the
# systemd unit installs to /etc/systemd/system.

set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/liwyd/mit-panel/main/agent"
INSTALL_DIR="/opt/mit-agent"
BIN_PATH="/usr/local/bin/mit-agent"
SERVICE_PATH="/etc/systemd/system/mit-agent.service"

PANEL_URL=""
AGENT_TOKEN=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url) PANEL_URL="$2"; shift 2 ;;
    --token) AGENT_TOKEN="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$PANEL_URL" || -z "$AGENT_TOKEN" ]]; then
  echo "Usage: install.sh --url <panel-url> --token <agent-token>" >&2
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "Run this script as root (needed for the reboot capability and the systemd unit)." >&2
  exit 1
fi

mkdir -p "$INSTALL_DIR"
curl -fsSL "$REPO_RAW/main.go" -o "$INSTALL_DIR/main.go"
curl -fsSL "$REPO_RAW/go.mod" -o "$INSTALL_DIR/go.mod"

GO_BIN="$(command -v go || true)"
if [[ -z "$GO_BIN" ]]; then
  echo "Go toolchain not found, installing it via the system package manager..."
  if command -v apt-get &>/dev/null; then
    apt-get update -qq && apt-get install -y golang-go
  elif command -v dnf &>/dev/null; then
    dnf install -y golang
  elif command -v yum &>/dev/null; then
    yum install -y golang
  elif command -v apk &>/dev/null; then
    apk add --no-cache go
  elif command -v pacman &>/dev/null; then
    pacman -Sy --noconfirm go
  else
    echo "No supported package manager found (apt/dnf/yum/apk/pacman)." >&2
    echo "Install a Go toolchain manually, then re-run this script." >&2
    exit 1
  fi
  hash -r
  GO_BIN="$(command -v go)"
fi

echo "Building agent with $("$GO_BIN" version)..."
(cd "$INSTALL_DIR" && CGO_ENABLED=0 "$GO_BIN" build -ldflags="-s -w" -o "$BIN_PATH" main.go)

rm -rf "$INSTALL_DIR"

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=MIT Panel monitoring agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN_PATH
Environment=PANEL_URL=$PANEL_URL
Environment=AGENT_TOKEN=$AGENT_TOKEN
Restart=always
RestartSec=5
User=root
MemoryMax=32M
Nice=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now mit-agent

echo "MIT Panel agent installed and running (systemctl status mit-agent)."
