#!/bin/bash
# MIT Panel - Installer & Manager
# https://github.com/liwyd/mit-panel

set -e

INSTALL_DIR="/opt/mit-panel"
REPO_URL="https://raw.githubusercontent.com/liwyd/mit-panel/main"
CONTAINER="mit-panel"
DATA="$INSTALL_DIR/data"

# ── Helpers ─────────────────────────────────────────────────────────────────────
running() { docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER}$"; }
exists()  { docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER}$"; }
installed() {
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/docker-compose.yml" ]; then return 0; fi
    if exists; then return 0; fi
    return 1
}

find_source_dir() {
    if [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        echo "$INSTALL_DIR"
        return
    fi
    local dir
    dir=$(docker inspect "$CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' 2>/dev/null || true)
    if [ -n "$dir" ] && [ -d "$dir" ]; then echo "$dir"; return; fi
    dir=$(docker inspect "$CONTAINER" --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null || true)
    if [ -n "$dir" ]; then
        dir=$(dirname "$dir")
        if [ -d "$dir" ]; then echo "$dir"; return; fi
    fi
    echo "$INSTALL_DIR"
}

get_ip() { curl -s --connect-timeout 4 ifconfig.me 2>/dev/null || echo "SERVER_IP"; }

ensure_docker() {
    if command -v docker &>/dev/null; then return; fi
    echo "  Docker not found. Installing..."
    curl -fsSL https://get.docker.com | bash >/dev/null 2>&1
    systemctl enable docker >/dev/null 2>&1
    systemctl start docker >/dev/null 2>&1
    echo "  Docker installed."
}

# ── Install ─────────────────────────────────────────────────────────────────────
do_install() {
    ensure_docker

    echo ""
    echo "--- Preparing ---"

    echo "  Cloning repository..."
    git clone --quiet "https://github.com/liwyd/mit-panel.git" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    mkdir -p "$DATA"
    echo "  Repository cloned."

    echo ""
    echo "--- Configuration ---"
    read -r -p "  Admin username [admin]: " USER </dev/tty
    USER=${USER:-admin}
    read -r -s -p "  Admin password [admin]: " PASS </dev/tty
    echo ""
    PASS=${PASS:-admin}
    read -r -p "  Panel port [8000]: " PORT </dev/tty
    PORT=${PORT:-8000}
    read -r -p "  URL path [dashboard]: " URLPATH </dev/tty
    URLPATH=${URLPATH:-dashboard}

    JWT_SECRET=$(openssl rand -hex 32)
    cp .env.example .env
    sed -i "s/^ADMIN_USERNAME=.*/ADMIN_USERNAME=$USER/" .env
    sed -i "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$PASS/" .env
    sed -i "s/^PORT=.*/PORT=$PORT/" .env
    sed -i "s/^URLPATH=.*/URLPATH=$URLPATH/" .env
    sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$JWT_SECRET\"|" .env
    echo "  Configuration saved."

    echo ""
    echo "--- Building ---"
    echo "  Building Docker image (this takes a while)..."
    docker compose build --no-cache >/dev/null 2>&1
    echo "  Image built."
    echo "  Starting container..."
    docker compose up -d >/dev/null 2>&1
    echo "  Container started."

    install_cli
    show_done "$PORT" "$URLPATH"
}

show_done() {
    local IP=$(get_ip)
    echo ""
    echo "========================================"
    echo "  Installation Complete!"
    echo "========================================"
    echo ""
    echo "  Panel URL: http://$IP:$1/$2/login"
    echo ""
    echo "  Command:   mit-panel"
    echo ""
}

install_cli() {
    local SRC
    SRC=$(find_source_dir)
    cat > /usr/local/bin/mit-panel << EOF
#!/bin/bash
cd "$SRC"
case "\${1:-}" in
    update)
        echo "Updating..."
        git pull
        docker compose down
        docker compose build --no-cache
        docker compose up -d
        echo "Done."
        ;;
    stop)    docker compose down && echo "Stopped." ;;
    start)   docker compose up -d && echo "Started." ;;
    restart) docker compose restart && echo "Restarted." ;;
    logs)    docker compose logs -f --tail=50 ;;
    status)  docker compose ps ;;
    uninstall)
        read -r -p "Are you sure? (y/N): " c
        if [ "\$c" = "y" ] || [ "\$c" = "Y" ]; then
            docker compose down -v
            rm -f /usr/local/bin/mit-panel
            echo "Uninstalled."
        fi
        ;;
    *) bash "$SRC/.tui.sh" ;;
esac
EOF
    chmod +x /usr/local/bin/mit-panel
    cp "$0" "$SRC/.tui.sh" 2>/dev/null || true
    chmod +x "$SRC/.tui.sh" 2>/dev/null || true
}

# ── Actions ─────────────────────────────────────────────────────────────────────
action_update() {
    local SRC
    SRC=$(find_source_dir)
    cd "$SRC"
    echo ""
    echo "========================================"
    echo "  Updating MIT Panel"
    echo "========================================"
    echo ""
    echo "  Pulling latest source code..."
    if [ -d .git ]; then
        git pull --quiet 2>/dev/null || {
            echo "  git pull failed, re-cloning..."
            cd /
            rm -rf "$SRC"
            git clone --quiet "https://github.com/liwyd/mit-panel.git" "$SRC"
            cd "$SRC"
        }
    else
        cd /
        rm -rf "$SRC"
        git clone --quiet "https://github.com/liwyd/mit-panel.git" "$SRC"
        cd "$SRC"
    fi
    echo "  Source code updated."

    if running; then
        echo "  Stopping container..."
        docker compose down >/dev/null 2>&1
        echo "  Container stopped."
    fi

    echo "  Rebuilding image..."
    docker compose build --no-cache >/dev/null 2>&1
    echo "  Image rebuilt."

    echo "  Starting container..."
    docker compose up -d >/dev/null 2>&1
    echo "  Container started."
    echo ""
    echo "  Update complete!"
    echo ""
}

action_stop() {
    if ! running; then echo "  Already stopped."; return; fi
    read -r -p "  Stop panel? [Y/n]: " c </dev/tty
    [[ "$c" =~ ^[nN] ]] && return
    cd "$(find_source_dir)"
    echo "  Stopping..."
    docker compose down >/dev/null 2>&1
    echo "  Stopped."
}

action_start() {
    if running; then echo "  Already running."; return; fi
    cd "$(find_source_dir)"
    echo "  Starting..."
    docker compose up -d >/dev/null 2>&1
    echo "  Started."
}

action_restart() {
    cd "$(find_source_dir)"
    echo "  Restarting..."
    docker compose restart >/dev/null 2>&1
    echo "  Restarted."
}

action_logs() {
    cd "$(find_source_dir)"
    docker compose logs -f --tail=50
}

action_env() {
    local SRC
    SRC=$(find_source_dir)
    echo ""
    echo "--- Current Settings ---"
    local U=$(grep "^ADMIN_USERNAME=" "$SRC/.env" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "admin")
    local P=$(grep "^PORT=" "$SRC/.env" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "8000")
    local PP=$(grep "^URLPATH=" "$SRC/.env" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "dashboard")
    echo "  Username:  $U"
    echo "  Password:  ********"
    echo "  Port:      $P"
    echo "  URL Path:  $PP"
    echo ""
    echo "  1.  Change username"
    echo "  2.  Change password"
    echo "  3.  Change port"
    echo "  4.  Change URL path"
    echo "  5.  Edit .env manually (nano)"
    echo ""
    read -r -p "  Choose [0]: " c </dev/tty
    c=${c:-0}

    case "$c" in
        1)
            read -r -p "  New username: " v </dev/tty
            [ -n "$v" ] && sed -i "s|^ADMIN_USERNAME=.*|ADMIN_USERNAME=${v}|" "$SRC/.env" && echo "  Updated."
            ;;
        2)
            read -r -s -p "  New password: " v </dev/tty
            echo ""
            [ -n "$v" ] && sed -i "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=${v}|" "$SRC/.env" && echo "  Updated."
            ;;
        3)
            read -r -p "  New port: " v </dev/tty
            [ -n "$v" ] && sed -i "s|^PORT=.*|PORT=${v}|" "$SRC/.env" && echo "  Updated."
            ;;
        4)
            read -r -p "  New URL path: " v </dev/tty
            [ -n "$v" ] && sed -i "s|^URLPATH=.*|URLPATH=${v}|" "$SRC/.env" && echo "  Updated."
            ;;
        5) ${EDITOR:-nano} "$SRC/.env" ;;
        0) return ;;
    esac

    if [ "$c" != "0" ] && [ "$c" != "5" ]; then
        echo ""
        read -r -p "  Restart now? [Y/n]: " r </dev/tty
        if [[ ! "$r" =~ ^[nN] ]]; then
            cd "$SRC"
            docker compose restart >/dev/null 2>&1
            echo "  Restarted."
        fi
    fi
}

action_uninstall() {
    local SRC
    SRC=$(find_source_dir)
    echo ""
    echo "  WARNING: All data will be deleted!"
    read -r -p "  Continue? [y/N]: " c </dev/tty
    [[ ! "$c" =~ ^[yY] ]] && return
    cd "$SRC"
    docker compose down -v >/dev/null 2>&1
    if [ "$SRC" = "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
    fi
    rm -f /usr/local/bin/mit-panel
    echo "  Uninstalled."
}

# ── Menu ────────────────────────────────────────────────────────────────────────
menu_installed() {
    local STATUS="running"
    if ! running; then
        if exists; then STATUS="stopped"; else STATUS="offline"; fi
    fi
    local SRC
    SRC=$(find_source_dir)

    echo ""
    echo "========================================"
    echo "  MIT Panel Manager"
    echo "========================================"
    echo ""
    echo "  Status:  $STATUS"
    echo "  Path:    $SRC"
    echo ""
    echo "  --- Actions ---"
    echo ""
    echo "  1.  Update"
    echo "  2.  Stop"
    echo "  3.  Start"
    echo "  4.  Restart"
    echo "  5.  Logs"
    echo "  6.  Settings"
    echo "  7.  Uninstall"
    echo ""
    echo "  0.  Exit"
    echo ""
    read -r -p "  Choose [0]: " c </dev/tty
    c=${c:-0}
    case "$c" in
        1) action_update ;;
        2) action_stop ;;
        3) action_start ;;
        4) action_restart ;;
        5) action_logs ;;
        6) action_env ;;
        7) action_uninstall ;;
    esac
}

menu_fresh() {
    if exists; then
        echo ""
        echo "========================================"
        echo "  Existing Container Detected"
        echo "========================================"
        echo ""
        echo "  A mit-panel container was found on this system."
        echo ""
        echo "  1.  Manage existing panel"
        echo "  2.  Fresh install (new)"
        echo ""
        echo "  0.  Exit"
        echo ""
        read -r -p "  Choose [0]: " c </dev/tty
        c=${c:-0}
        case "$c" in
            1) return ;;
            2) do_install ;;
        esac
    else
        echo ""
        echo "========================================"
        echo "  MIT Panel Installer"
        echo "========================================"
        echo ""
        echo "  MIT Panel is not installed yet."
        echo ""
        echo "  1.  Install"
        echo ""
        echo "  0.  Exit"
        echo ""
        read -r -p "  Choose [0]: " c </dev/tty
        c=${c:-0}
        [ "$c" = "1" ] && do_install
    fi
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
    if [[ $EUID -ne 0 ]]; then
        echo "  Error: This script must be run as root."
        echo "  Run with: sudo bash install.sh"
        exit 1
    fi

    while true; do
        if installed; then menu_installed; else menu_fresh; fi
    done
}

main "$@"
