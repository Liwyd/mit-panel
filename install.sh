#!/bin/bash
# MIT Panel - Installer & Manager
# https://github.com/liwyd/mit-panel

set -euo pipefail

INSTALL_DIR="/opt/mit-panel"
REPO_URL="https://raw.githubusercontent.com/liwyd/mit-panel/main"
CONTAINER="mit-panel"
DATA="$INSTALL_DIR/data"

# ── Colors ──────────────────────────────────────────────────────────────────────
R='\033[0m'
B='\033[1m'
D='\033[2m'
C='\033[36m'
G='\033[32m'
Y='\033[33m'
RD='\033[31m'
DM='\033[90m'

# ── Helpers ─────────────────────────────────────────────────────────────────────
input() { read -r "$@" < /dev/tty; }
secret() { read -rs "$@" < /dev/tty; echo ""; }
clr() { printf '\033[2J\033[H'; }

line() { printf "${DM}  --------------------------------------------------${R}\n"; }
pad()  { printf "\n"; }

title() {
    clr
    pad
    printf "  ${C}${B}mit${R}${D}panel${R}\n"
    [ -n "${1:-}" ] && printf "  ${DM}  $1${R}\n"
    line
}

ok()   { printf "  ${G}[+]${R} $1\n"; }
fail() { printf "  ${RD}[-]${R} $1\n"; }
info() { printf "  ${DM}    $1${R}\n"; }
warn() { printf "  ${Y}[!]${R} ${Y}$1${R}\n"; }
ask()  { printf "  ${DM}  > $1${R} "; }

spin() {
    local msg="$1" chars='|/-\' i=0
    while true; do printf "\r  ${C}${chars:i++%${#chars}:1}${R} ${DM}${msg}...${R}"; sleep 0.1; done
}

die() { fail "$1"; show_cursor; exit 1; }

show_cursor() { tput cnorm 2>/dev/null; }
hide_cursor() { tput civis 2>/dev/null; }

running() { docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER}$"; }
exists()  { docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER}$"; }
installed() { [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/docker-compose.yml" ]; }

get_ip() { curl -s --connect-timeout 4 ifconfig.me 2>/dev/null || echo "SERVER_IP"; }

# ── Docker ──────────────────────────────────────────────────────────────────────
ensure_docker() {
    if command -v docker &>/dev/null; then return; fi
    title "installing docker"
    info "Docker not found, installing..."
    pad
    spin "Downloading Docker" &
    SPIN_PID=$!
    curl -fsSL https://get.docker.com | bash >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Docker installed"
    systemctl enable docker >/dev/null 2>&1
    systemctl start docker >/dev/null 2>&1
    sleep 0.5
}

# ── Env ─────────────────────────────────────────────────────────────────────────
env_set() {
    local k="$1" v="$2"
    if grep -q "^${k}=" "$INSTALL_DIR/.env" 2>/dev/null; then
        sed -i "s|^${k}=.*|${k}=${v}|" "$INSTALL_DIR/.env"
    else
        echo "${k}=${v}" >> "$INSTALL_DIR/.env"
    fi
}

env_get() {
    grep "^${1}=" "$INSTALL_DIR/.env" 2>/dev/null | head -1 | cut -d'=' -f2- || echo "${2:-}"
}

setup_env() {
    local user="${1:-admin}" pass="${2:-admin}" port="${3:-8000}" path="${4:-dashboard}"
    local secret=$(openssl rand -hex 32)
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    env_set ADMIN_USERNAME "$user"
    env_set ADMIN_PASSWORD "$pass"
    env_set PORT "$port"
    env_set URLPATH "$path"
    env_set JWT_SECRET_KEY "\"$secret\""
}

# ── Install ─────────────────────────────────────────────────────────────────────
do_install() {
    ensure_docker

    title "preparing"
    mkdir -p "$DATA"

    spin "Downloading files" &
    SPIN_PID=$!
    curl -fsSL "$REPO_URL/docker-compose.yml" -o "$INSTALL_DIR/docker-compose.yml"
    curl -fsSL "$REPO_URL/.env.example" -o "$INSTALL_DIR/.env.example"
    curl -fsSL "$REPO_URL/entrypoint.sh" -o "$INSTALL_DIR/entrypoint.sh"
    chmod +x "$INSTALL_DIR/entrypoint.sh"
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Files downloaded"
    sleep 0.3

    # Config
    title "configuration"
    ask "admin username  [admin]"; input user; user="${user:-admin}"
    ask "admin password  [admin]"; secret pass; pass="${pass:-admin}"
    ask "port            [8000]"; input port; port="${port:-8000}"
    ask "url path        [dashboard]"; input path; path="${path:-dashboard}"
    pad
    setup_env "$user" "$pass" "$port" "$path"
    ok "Configuration saved"
    sleep 0.3

    # Build
    title "building"
    cd "$INSTALL_DIR"
    spin "Building image" &
    SPIN_PID=$!
    docker compose build --no-cache >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Image built"
    sleep 0.3

    spin "Starting container" &
    SPIN_PID=$!
    docker compose up -d >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Container started"

    install_cli
    show_done "$port" "$path"
}

show_done() {
    local ip=$(get_ip)
    title "done"
    pad
    printf "  ${G}MIT Panel is live${R}\n"
    pad
    printf "  ${C}http://${ip}:${1}/${2}/login${R}\n"
    pad
    line
    info "Run ${C}mit-panel${R} to manage"
    pad
    show_cursor
}

install_cli() {
    cat > /usr/local/bin/mit-panel << 'EOF'
#!/bin/bash
cd /opt/mit-panel
case "${1:-}" in
    update)
        echo "Updating..."
        docker compose down
        curl -fsSL https://raw.githubusercontent.com/liwyd/mit-panel/main/docker-compose.yml -o docker-compose.yml
        curl -fsSL https://raw.githubusercontent.com/liwyd/mit-panel/main/entrypoint.sh -o entrypoint.sh
        chmod +x entrypoint.sh
        docker compose build --no-cache
        docker compose up -d
        echo "Done"
        ;;
    stop)    docker compose down && echo "Stopped" ;;
    start)   docker compose up -d && echo "Started" ;;
    restart) docker compose restart && echo "Restarted" ;;
    logs)    docker compose logs -f --tail=50 ;;
    status)  docker compose ps ;;
    uninstall)
        read -p "Are you sure? (y/N): " c
        if [ "$c" = "y" ] || [ "$c" = "Y" ]; then
            docker compose down -v
            rm -rf /opt/mit-panel
            rm -f /usr/local/bin/mit-panel
            echo "Uninstalled"
        fi
        ;;
    *) bash /opt/mit-panel/.tui.sh ;;
esac
EOF
    chmod +x /usr/local/bin/mit-panel
    cp "$0" "$INSTALL_DIR/.tui.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/.tui.sh" 2>/dev/null || true
}

# ── Actions ─────────────────────────────────────────────────────────────────────
action_update() {
    title "updating"
    cd "$INSTALL_DIR"
    spin "Pulling latest" &
    SPIN_PID=$!
    curl -fsSL "$REPO_URL/docker-compose.yml" -o docker-compose.yml
    curl -fsSL "$REPO_URL/entrypoint.sh" -o entrypoint.sh
    chmod +x entrypoint.sh
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Files updated"

    if running; then
        spin "Stopping" &
        SPIN_PID=$!
        docker compose down >/dev/null 2>&1
        kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
        printf "\r"
        ok "Stopped"
    fi

    spin "Rebuilding" &
    SPIN_PID=$!
    docker compose build --no-cache >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Rebuilt"

    spin "Starting" &
    SPIN_PID=$!
    docker compose up -d >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Updated and running"
    sleep 0.8
}

action_stop() {
    title "stop"
    if ! running; then warn "Already stopped"; sleep 0.5; return; fi
    ask "Stop panel? [Y/n]"; input c
    [[ "$c" =~ ^[nN] ]] && return
    cd "$INSTALL_DIR"
    spin "Stopping" &
    SPIN_PID=$!
    docker compose down >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Stopped"
    sleep 0.5
}

action_start() {
    title "start"
    if running; then warn "Already running"; sleep 0.5; return; fi
    cd "$INSTALL_DIR"
    spin "Starting" &
    SPIN_PID=$!
    docker compose up -d >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Started"
    sleep 0.5
}

action_restart() {
    title "restart"
    cd "$INSTALL_DIR"
    spin "Restarting" &
    SPIN_PID=$!
    docker compose restart >/dev/null 2>&1
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Restarted"
    sleep 0.5
}

action_logs() {
    title "logs  (ctrl+c to exit)"
    cd "$INSTALL_DIR"
    docker compose logs -f --tail=50
}

action_env() {
    while true; do
        title "settings"
        local u=$(env_get ADMIN_USERNAME "admin")
        local p=$(env_get PORT "8000")
        local pp=$(env_get URLPATH "dashboard")

        printf "  ${DM}  username${R}    ${C}${u}${R}\n"
        printf "  ${DM}  password${R}    ${C}****${R}\n"
        printf "  ${DM}  port${R}        ${C}${p}${R}\n"
        printf "  ${DM}  url path${R}    ${C}${pp}${R}\n"
        pad
        line
        printf "  ${G}  1${R}  username\n"
        printf "  ${G}  2${R}  password\n"
        printf "  ${G}  3${R}  port\n"
        printf "  ${G}  4${R}  url path\n"
        printf "  ${G}  5${R}  edit manually ${D}(nano)${R}\n"
        printf "  ${RD}  0${R}  back\n"
        pad
        ask "select"; input c
        pad

        case "$c" in
            1) ask "new username"; input v; [ -n "$v" ] && env_set ADMIN_USERNAME "$v" && ok "Updated"; sleep 0.3 ;;
            2) ask "new password"; secret v; [ -n "$v" ] && env_set ADMIN_PASSWORD "$v" && ok "Updated"; sleep 0.3 ;;
            3) ask "new port"; input v; [ -n "$v" ] && env_set PORT "$v" && ok "Updated"; sleep 0.3 ;;
            4) ask "new url path"; input v; [ -n "$v" ] && env_set URLPATH "$v" && ok "Updated"; sleep 0.3 ;;
            5) ${EDITOR:-nano} "$INSTALL_DIR/.env"; sleep 0.3 ;;
            0) return ;;
        esac

        if [ "$c" != "0" ] && [ "$c" != "5" ]; then
            pad
            ask "restart now? [Y/n]"; input r
            if [[ ! "$r" =~ ^[nN] ]]; then
                cd "$INSTALL_DIR"
                spin "Restarting" &
                SPIN_PID=$!
                docker compose restart >/dev/null 2>&1
                kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
                printf "\r"
                ok "Restarted"
                sleep 0.5
            fi
        fi
    done
}

action_uninstall() {
    title "uninstall"
    warn "All data will be deleted"
    ask "Continue? [y/N]"; input c
    [[ ! "$c" =~ ^[yY] ]] && return
    cd "$INSTALL_DIR"
    spin "Removing" &
    SPIN_PID=$!
    docker compose down -v >/dev/null 2>&1
    rm -rf "$INSTALL_DIR"
    rm -f /usr/local/bin/mit-panel
    kill $SPIN_PID 2>/dev/null; wait $SPIN_PID 2>/dev/null
    printf "\r"
    ok "Uninstalled"
    sleep 0.5
}

# ── Menu ────────────────────────────────────────────────────────────────────────
menu_installed() {
    local st="${G}[running]${R}"
    if ! running; then
        if exists; then st="${Y}[stopped]${R}"; else st="${RD}[offline]${R}"; fi
    fi

    title "menu"
    printf "  ${DM}  status${R}   ${st}\n"
    pad
    line
    printf "  ${G}  1${R}   update\n"
    printf "  ${G}  2${R}   stop\n"
    printf "  ${G}  3${R}   start\n"
    printf "  ${G}  4${R}   restart\n"
    printf "  ${G}  5${R}   logs\n"
    printf "  ${G}  6${R}   settings\n"
    printf "  ${G}  7${R}   uninstall\n"
    printf "  ${RD}  0${R}   exit\n"
    pad
    ask "select"; input c
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
    title "welcome"
    pad
    printf "  ${DM}  MIT Panel is not installed.${R}\n"
    pad
    line
    printf "  ${G}  1${R}   install\n"
    printf "  ${RD}  0${R}   exit\n"
    pad
    ask "select"; input c
    [ "$c" = "1" ] && do_install
}

# ── Main ────────────────────────────────────────────────────────────────────────
main() {
    trap 'show_cursor; exit 0' INT TERM
    hide_cursor

    if [[ $EUID -ne 0 ]]; then
        title "error"
        die "Run with: sudo bash install.sh"
    fi

    while true; do
        if installed; then menu_installed; else menu_fresh; fi
    done
}

main "$@"
