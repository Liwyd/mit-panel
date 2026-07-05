#!/bin/bash

# MIT Panel - Installer & Manager
# https://github.com/liwyd/mit-panel

set -euo pipefail

# ─── Config ────────────────────────────────────────────────────────────────────
INSTALL_DIR="/opt/mit-panel"
REPO_URL="https://raw.githubusercontent.com/liwyd/mit-panel/main"
GITHUB_REPO="https://github.com/liwyd/mit-panel"
CONTAINER_NAME="mit-panel"
SERVICE_NAME="mit-panel"
DATA_DIR="$INSTALL_DIR/data"

# ─── Colors ────────────────────────────────────────────────────────────────────
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_DIM='\033[2m'
C_CYAN='\033[36m'
C_GREEN='\033[32m'
C_YELLOW='\033[33m'
C_RED='\033[31m'
C_BLUE='\033[34m'
C_MAGENTA='\033[35m'
C_WHITE='\033[97m'
C_BG_DARK='\033[48;5;236m'
C_GRAY='\033[90m'
C_TEAL='\033[38;5;80m'

# ─── Box Drawing ───────────────────────────────────────────────────────────────
B_TL="╔"
B_TR="╗"
B_BL="╚"
B_BR="╝"
B_H="═"
B_V="║"
B_T="╠"
B_TT="╣"

# ─── UI Functions ──────────────────────────────────────────────────────────────
clear_screen() {
    clear
    tput civis 2>/dev/null || true
}

show_cursor() {
    tput cnorm 2>/dev/null || true
}

print_centered() {
    local text="$1"
    local color="${2:-$C_WHITE}"
    local width=60
    local padding=$(( (width - ${#text}) / 2 ))
    printf "${color}%${padding}s%s%$((width - padding - ${#text}))s${C_RESET}\n" "" "$text" ""
}

draw_box_top() {
    local width=60
    printf "${C_CYAN}"
    printf "$B_TL"
    printf "${B_H}%.0s" $(seq 1 $((width - 2)))
    printf "$B_TR"
    printf "${C_RESET}\n"
}

draw_box_bottom() {
    local width=60
    printf "${C_CYAN}"
    printf "$B_BL"
    printf "${B_H}%.0s" $(seq 1 $((width - 2)))
    printf "$B_BR"
    printf "${C_RESET}\n"
}

draw_box_line() {
    local content="$1"
    local width=60
    local content_width=$((width - 4))
    printf "${C_CYAN}${B_V}${C_RESET}  "
    printf "${content}"
    local pad=$((content_width - ${#content}))
    if [ $pad -gt 0 ]; then
        printf "%${pad}s" ""
    fi
    printf "  ${C_CYAN}${B_V}${C_RESET}\n"
}

draw_box_line_color() {
    local content="$1"
    local color="$2"
    local width=60
    local content_width=$((width - 4))
    printf "${C_CYAN}${B_V}${C_RESET}  "
    printf "${color}${content}${C_RESET}"
    local stripped_content=$(echo -e "$content" | sed 's/\x1b\[[0-9;]*m//g')
    local pad=$((content_width - ${#stripped_content}))
    if [ $pad -gt 0 ]; then
        printf "%${pad}s" ""
    fi
    printf "  ${C_CYAN}${B_V}${C_RESET}\n"
}

draw_separator() {
    local width=60
    printf "${C_CYAN}"
    printf "$B_T"
    printf "${B_H}%.0s" $(seq 1 $((width - 2)))
    printf "$B_TT"
    printf "${C_RESET}\n"
}

draw_empty_line() {
    local width=60
    printf "${C_CYAN}${B_V}${C_RESET}"
    printf "%$((width - 2))s"
    printf "${C_CYAN}${B_V}${C_RESET}\n"
}

show_header() {
    local subtitle="${1:-}"
    clear_screen
    draw_box_top
    draw_empty_line
    draw_box_line_color "  MIT Panel" "${C_CYAN}${C_BOLD}"
    draw_box_line_color "  VPN Panel Manager" "${C_DIM}"
    draw_empty_line
    draw_separator
    if [ -n "$subtitle" ]; then
        draw_box_line_color "  $subtitle" "${C_YELLOW}"
    fi
}

show_status() {
    local msg="$1"
    local icon="$2"
    local color="$3"
    printf "  ${color}${icon}${C_RESET} ${C_WHITE}%s${C_RESET}" "$msg"
}

spinner() {
    local msg="$1"
    local spin_chars="⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    local i=0
    while true; do
        printf "\r  ${C_CYAN}${spin_chars:i++%${#spin_chars}:1}${C_RESET} ${C_DIM}%s${C_RESET}" "$msg"
        sleep 0.1
    done
}

print_success() {
    printf "\r  ${C_GREEN}✓${C_RESET} ${C_WHITE}%s${C_RESET}\n" "$1"
}

print_error() {
    printf "\r  ${C_RED}✗${C_RESET} ${C_WHITE}%s${C_RESET}\n" "$1"
}

print_info() {
    printf "  ${C_BLUE}ℹ${C_RESET} ${C_DIM}%s${C_RESET}\n" "$1"
}

print_warning() {
    printf "  ${C_YELLOW}⚠${C_RESET} ${C_YELLOW}%s${C_RESET}\n" "$1"
}

# ─── System Checks ─────────────────────────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        show_header "Error"
        draw_box_top
        draw_empty_line
        draw_box_line_color "  ${C_RED}Root privileges required${C_RESET}" ""
        draw_empty_line
        draw_separator
        draw_box_line_color "  Run with: sudo bash install.sh" "${C_DIM}"
        draw_empty_line
        draw_box_bottom
        show_cursor
        exit 1
    fi
}

check_docker() {
    if command -v docker &>/dev/null; then
        return 0
    fi
    return 1
}

install_docker() {
    show_header "Installing Docker"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  Docker is not installed on your system." "${C_YELLOW}"
    draw_box_line_color "  It will be installed automatically." "${C_DIM}"
    draw_empty_line
    draw_box_bottom
    echo ""
    spinner "Downloading Docker installer..."
    curl -fsSL https://get.docker.com | sh >/dev/null 2>&1
    print_success "Docker installed successfully"

    spinner "Enabling Docker service..."
    systemctl enable docker >/dev/null 2>&1
    systemctl start docker >/dev/null 2>&1
    print_success "Docker service started"
    sleep 1
}

check_docker_compose() {
    if docker compose version &>/dev/null 2>&1; then
        return 0
    fi
    return 1
}

is_container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"
}

is_container_exists() {
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^${CONTAINER_NAME}$"
}

is_installed() {
    [ -d "$INSTALL_DIR" ] && [ -f "$INSTALL_DIR/docker-compose.yml" ]
}

# ─── Installation ──────────────────────────────────────────────────────────────
setup_directory() {
    spinner "Creating installation directory..."
    mkdir -p "$DATA_DIR"
    print_success "Directory ready: $INSTALL_DIR"
}

download_files() {
    spinner "Downloading docker-compose.yml..."
    curl -fsSL "$REPO_URL/docker-compose.yml" -o "$INSTALL_DIR/docker-compose.yml"
    print_success "docker-compose.yml downloaded"

    spinner "Downloading .env.example..."
    curl -fsSL "$REPO_URL/.env.example" -o "$INSTALL_DIR/.env.example"
    print_success ".env.example downloaded"

    spinner "Downloading entrypoint.sh..."
    curl -fsSL "$REPO_URL/entrypoint.sh" -o "$INSTALL_DIR/entrypoint.sh"
    chmod +x "$INSTALL_DIR/entrypoint.sh"
    print_success "entrypoint.sh downloaded"
}

configure_env() {
    local admin_user="${1:-admin}"
    local admin_pass="${2:-admin}"
    local port="${3:-8000}"
    local url_path="${4:-dashboard}"
    local jwt_secret=$(openssl rand -hex 32)

    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    sed -i "s/^ADMIN_USERNAME=.*/ADMIN_USERNAME=$admin_user/" "$INSTALL_DIR/.env"
    sed -i "s/^ADMIN_PASSWORD=.*/ADMIN_PASSWORD=$admin_pass/" "$INSTALL_DIR/.env"
    sed -i "s/^PORT=.*/PORT=$port/" "$INSTALL_DIR/.env"
    sed -i "s/^URLPATH=.*/URLPATH=$url_path/" "$INSTALL_DIR/.env"
    sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=\"$jwt_secret\"|" "$INSTALL_DIR/.env"
}

update_env_value() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" "$INSTALL_DIR/.env"; then
        sed -i "s|^${key}=.*|${key}=${value}|" "$INSTALL_DIR/.env"
    else
        echo "${key}=${value}" >> "$INSTALL_DIR/.env"
    fi
}

build_and_run() {
    cd "$INSTALL_DIR"
    spinner "Building Docker image (this may take a while)..."
    docker compose build --no-cache >/dev/null 2>&1
    print_success "Docker image built"

    spinner "Starting MIT Panel..."
    docker compose up -d >/dev/null 2>&1
    print_success "MIT Panel is running"
}

# ─── TUI Menu ──────────────────────────────────────────────────────────────────
menu_fresh_install() {
    local admin_user="admin"
    local admin_pass="admin"
    local port="8000"
    local url_path="dashboard"

    # ── Step 1: Docker ──
    if ! check_docker; then
        install_docker
    else
        show_header "Docker Check"
        draw_box_top
        draw_empty_line
        draw_box_line_color "  ${C_GREEN}Docker is installed${C_RESET}" ""
        draw_empty_line
        draw_box_bottom
        sleep 1
    fi

    # ── Step 2: Directory ──
    show_header "Preparing Installation"
    draw_box_top
    draw_empty_line
    draw_empty_line
    draw_empty_line
    draw_box_bottom
    echo ""
    setup_directory
    download_files
    sleep 1

    # ── Step 3: Configuration ──
    show_header "Configuration"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  Enter panel configuration:" "${C_CYAN}"
    draw_empty_line
    draw_box_bottom
    echo ""

    printf "  ${C_DIM}Admin username [${C_GREEN}admin${C_DIM}]: ${C_RESET}"
    read -r input
    admin_user="${input:-$admin_user}"

    printf "  ${C_DIM}Admin password [${C_GREEN}admin${C_DIM}]: ${C_RESET}"
    read -rs input
    echo ""
    admin_pass="${input:-$admin_pass}"

    printf "  ${C_DIM}Panel port [${C_GREEN}8000${C_DIM}]: ${C_RESET}"
    read -r input
    port="${input:-$port}"

    printf "  ${C_DIM}URL path [${C_GREEN}dashboard${C_DIM}]: ${C_RESET}"
    read -r input
    url_path="${input:-$url_path}"

    echo ""
    configure_env "$admin_user" "$admin_pass" "$port" "$url_path"
    print_success "Configuration saved"
    sleep 1

    # ── Step 4: Build & Run ──
    show_header "Building & Starting"
    draw_box_top
    draw_empty_line
    draw_empty_line
    draw_empty_line
    draw_box_bottom
    echo ""
    build_and_run

    # ── Done ──
    show_install_complete "$port" "$url_path"
}

show_install_complete() {
    local port="$1"
    local url_path="$2"
    local ip=$(curl -s --connect-timeout 5 ifconfig.me 2>/dev/null || echo "YOUR_SERVER_IP")

    show_header "Installation Complete"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}MIT Panel is now running!${C_RESET}" ""
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  Panel URL:" "${C_DIM}"
    draw_box_line_color "  ${C_CYAN}http://$ip:$port/$url_path/login${C_RESET}" ""
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  Quick commands:" "${C_DIM}"
    draw_box_line_color "  ${C_GREEN}mit-panel${C_RESET}          Show management menu" ""
    draw_box_line_color "  ${C_GREEN}mit-panel logs${C_RESET}       View container logs" ""
    draw_box_line_color "  ${C_GREEN}mit-panel restart${C_RESET}     Restart the panel" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    install_mit_panel_command
    show_cursor
}

menu_update() {
    show_header "Updating MIT Panel"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  Pulling latest changes..." "${C_CYAN}"
    draw_empty_line
    draw_box_bottom
    echo ""

    cd "$INSTALL_DIR"

    spinner "Downloading latest files..."
    curl -fsSL "$REPO_URL/docker-compose.yml" -o docker-compose.yml
    curl -fsSL "$REPO_URL/.env.example" -o .env.example
    curl -fsSL "$REPO_URL/entrypoint.sh" -o entrypoint.sh
    chmod +x entrypoint.sh
    print_success "Files updated"

    if is_container_running; then
        spinner "Stopping container..."
        docker compose down >/dev/null 2>&1
        print_success "Container stopped"
    fi

    spinner "Rebuilding image..."
    docker compose build --no-cache >/dev/null 2>&1
    print_success "Image rebuilt"

    spinner "Starting container..."
    docker compose up -d >/dev/null 2>&1
    print_success "MIT Panel updated and running"

    sleep 1
    show_header "Update Complete"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}MIT Panel updated successfully!${C_RESET}" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    show_cursor
}

menu_stop() {
    show_header "Stopping MIT Panel"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  ${C_YELLOW}Are you sure?${C_RESET}" ""
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}[1]${C_RESET}  Yes, stop the panel" ""
    draw_box_line_color "  ${C_RED}[2]${C_RESET}  No, go back" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    printf "  ${C_DIM}Select: ${C_RESET}"
    read -r choice

    case "$choice" in
        1)
            cd "$INSTALL_DIR"
            spinner "Stopping container..."
            docker compose down >/dev/null 2>&1
            print_success "MIT Panel stopped"
            sleep 1
            ;;
        *)
            return
            ;;
    esac
}

menu_start() {
    show_header "Starting MIT Panel"
    cd "$INSTALL_DIR"

    if is_container_running; then
        draw_box_top
        draw_empty_line
        draw_box_line_color "  ${C_YELLOW}Container is already running${C_RESET}" ""
        draw_empty_line
        draw_box_bottom
        echo ""
        sleep 1
        return
    fi

    draw_box_top
    draw_empty_line
    draw_empty_line
    draw_empty_line
    draw_box_bottom
    echo ""

    spinner "Starting container..."
    docker compose up -d >/dev/null 2>&1
    print_success "MIT Panel started"
    sleep 1
}

menu_restart() {
    show_header "Restarting MIT Panel"
    cd "$INSTALL_DIR"

    draw_box_top
    draw_empty_line
    draw_empty_line
    draw_empty_line
    draw_box_bottom
    echo ""

    spinner "Restarting container..."
    docker compose restart >/dev/null 2>&1
    print_success "MIT Panel restarted"
    sleep 1
}

menu_view_logs() {
    show_header "MIT Panel Logs"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  Press ${C_CYAN}Ctrl+C${C_RESET} to exit logs" "${C_DIM}"
    draw_empty_line
    draw_box_bottom
    echo ""
    cd "$INSTALL_DIR"
    docker compose logs -f --tail=50
}

menu_edit_env() {
    show_header "Environment Variables"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  Current .env configuration:" "${C_CYAN}"
    draw_empty_line
    draw_separator
    draw_empty_line

    if [ -f "$INSTALL_DIR/.env" ]; then
        while IFS= read -r line; do
            if [[ "$line" == \#* ]] || [[ -z "$line" ]]; then
                draw_box_line_color "  ${C_DIM}$line${C_RESET}" ""
            else
                local key=$(echo "$line" | cut -d'=' -f1)
                local val=$(echo "$line" | cut -d'=' -f2-)
                case "$key" in
                    ADMIN_PASSWORD|JWT_SECRET_KEY)
                        draw_box_line_color "  ${C_GREEN}$key${C_RESET}=${C_DIM}***${C_RESET}" ""
                        ;;
                    *)
                        draw_box_line_color "  ${C_GREEN}$key${C_RESET}=${C_WHITE}$val${C_RESET}" ""
                        ;;
                esac
            fi
        done < "$INSTALL_DIR/.env"
    else
        draw_box_line_color "  ${C_RED}.env file not found${C_RESET}" ""
    fi

    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}[1]${C_RESET}  Change admin username" ""
    draw_box_line_color "  ${C_GREEN}[2]${C_RESET}  Change admin password" ""
    draw_box_line_color "  ${C_GREEN}[3]${C_RESET}  Change port" ""
    draw_box_line_color "  ${C_GREEN}[4]${C_RESET}  Change URL path" ""
    draw_box_line_color "  ${C_GREEN}[5]${C_RESET}  Edit .env manually (nano)" ""
    draw_box_line_color "  ${C_RED}[0]${C_RESET}  Back to menu" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    printf "  ${C_DIM}Select: ${C_RESET}"
    read -r choice

    cd "$INSTALL_DIR"
    case "$choice" in
        1)
            printf "  ${C_DIM}New username: ${C_RESET}"
            read -r val
            [ -n "$val" ] && update_env_value "ADMIN_USERNAME" "$val" && print_success "Updated"
            ;;
        2)
            printf "  ${C_DIM}New password: ${C_RESET}"
            read -rs val
            echo ""
            [ -n "$val" ] && update_env_value "ADMIN_PASSWORD" "$val" && print_success "Updated"
            ;;
        3)
            printf "  ${C_DIM}New port: ${C_RESET}"
            read -r val
            [ -n "$val" ] && update_env_value "PORT" "$val" && print_success "Updated"
            ;;
        4)
            printf "  ${C_DIM}New URL path: ${C_RESET}"
            read -r val
            [ -n "$val" ] && update_env_value "URLPATH" "$val" && print_success "Updated"
            ;;
        5)
            ${EDITOR:-nano} "$INSTALL_DIR/.env"
            ;;
        0|*)
            return
            ;;
    esac

    echo ""
    draw_box_top
    draw_empty_line
    draw_box_line_color "  ${C_YELLOW}Restart to apply changes?${C_RESET}" ""
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}[1]${C_RESET}  Yes, restart now" ""
    draw_box_line_color "  ${C_RED}[2]${C_RESET}  No, later" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    printf "  ${C_DIM}Select: ${C_RESET}"
    read -r restart_choice
    if [ "$restart_choice" = "1" ]; then
        spinner "Restarting..."
        docker compose restart >/dev/null 2>&1
        print_success "Restarted with new settings"
    fi
    sleep 1
}

menu_uninstall() {
    show_header "Uninstall MIT Panel"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  ${C_RED}Warning: This will delete all data!${C_RESET}" ""
    draw_box_line_color "  ${C_DIM}Database, logs, and settings will be lost.${C_RESET}" ""
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}[1]${C_RESET}  Yes, uninstall everything" ""
    draw_box_line_color "  ${C_RED}[2]${C_RESET}  No, go back" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    printf "  ${C_DIM}Select: ${C_RESET}"
    read -r choice

    case "$choice" in
        1)
            cd "$INSTALL_DIR"
            spinner "Stopping container..."
            docker compose down -v >/dev/null 2>&1
            print_success "Container stopped"

            spinner "Removing installation..."
            rm -rf "$INSTALL_DIR"
            rm -f /usr/local/bin/mit-panel
            print_success "MIT Panel uninstalled"

            sleep 1
            show_header "Uninstalled"
            draw_box_top
            draw_empty_line
            draw_box_line_color "  ${C_GREEN}MIT Panel has been removed.${C_RESET}" ""
            draw_empty_line
            draw_box_bottom
            echo ""
            show_cursor
            exit 0
            ;;
        *)
            return
            ;;
    esac
}

install_mit_panel_command() {
    cat > /usr/local/bin/mit-panel << 'SCRIPT'
#!/bin/bash
cd /opt/mit-panel

case "${1:-menu}" in
    menu|"")
        exec bash /opt/mit-panel/.mit-panel-menu.sh
        ;;
    update)
        echo "Updating MIT Panel..."
        docker compose down
        curl -fsSL https://raw.githubusercontent.com/liwyd/mit-panel/main/docker-compose.yml -o docker-compose.yml
        curl -fsSL https://raw.githubusercontent.com/liwyd/mit-panel/main/entrypoint.sh -o entrypoint.sh
        chmod +x entrypoint.sh
        docker compose build --no-cache
        docker compose up -d
        echo "Update complete!"
        ;;
    stop)
        docker compose down
        echo "MIT Panel stopped"
        ;;
    start)
        docker compose up -d
        echo "MIT Panel started"
        ;;
    restart)
        docker compose restart
        echo "MIT Panel restarted"
        ;;
    logs)
        docker compose logs -f --tail=50
        ;;
    status)
        docker compose ps
        ;;
    uninstall)
        echo "Are you sure? (y/N): "
        read -r confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            docker compose down -v
            rm -rf /opt/mit-panel
            rm -f /usr/local/bin/mit-panel
            echo "MIT Panel uninstalled"
        fi
        ;;
    *)
        echo "MIT Panel Manager"
        echo ""
        echo "Usage: mit-panel [command]"
        echo ""
        echo "Commands:"
        echo "  menu        Show management menu (default)"
        echo "  update      Update to latest version"
        echo "  stop        Stop the panel"
        echo "  start       Start the panel"
        echo "  restart     Restart the panel"
        echo "  logs        View container logs"
        echo "  status      Show container status"
        echo "  uninstall   Remove MIT Panel"
        ;;
esac
SCRIPT
    chmod +x /usr/local/bin/mit-panel

    # Save the menu script for the mit-panel command
    cp "$0" "$INSTALL_DIR/.mit-panel-menu.sh" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/.mit-panel-menu.sh" 2>/dev/null || true
}

# ─── Main Menu ─────────────────────────────────────────────────────────────────
show_main_menu_installed() {
    local status_color="${C_GREEN}"
    local status_icon="●"
    local status_text="Running"

    if is_container_running; then
        status_color="${C_GREEN}"
        status_icon="●"
        status_text="Running"
    elif is_container_exists; then
        status_color="${C_YELLOW}"
        status_icon="●"
        status_text="Stopped"
    else
        status_color="${C_RED}"
        status_icon="●"
        status_text="Not running"
    fi

    show_header "Main Menu"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  Status: ${status_color}${status_icon} ${status_text}${C_RESET}" ""
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}[1]${C_RESET}  Update panel" ""
    draw_box_line_color "  ${C_GREEN}[2]${C_RESET}  Stop panel" ""
    draw_box_line_color "  ${C_GREEN}[3]${C_RESET}  Start panel" ""
    draw_box_line_color "  ${C_GREEN}[4]${C_RESET}  Restart panel" ""
    draw_box_line_color "  ${C_GREEN}[5]${C_RESET}  View logs" ""
    draw_box_line_color "  ${C_GREEN}[6]${C_RESET}  Edit .env" ""
    draw_box_line_color "  ${C_GREEN}[7]${C_RESET}  Uninstall" ""
    draw_box_line_color "  ${C_RED}[0]${C_RESET}  Exit" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    printf "  ${C_DIM}Select: ${C_RESET}"
}

show_main_menu_not_installed() {
    show_header "Welcome"
    draw_box_top
    draw_empty_line
    draw_box_line_color "  MIT Panel is not installed on this system." "${C_YELLOW}"
    draw_box_line_color "  Would you like to install it?" "${C_DIM}"
    draw_empty_line
    draw_separator
    draw_empty_line
    draw_box_line_color "  ${C_GREEN}[1]${C_RESET}  Install MIT Panel" ""
    draw_box_line_color "  ${C_RED}[0]${C_RESET}  Exit" ""
    draw_empty_line
    draw_box_bottom
    echo ""
    printf "  ${C_DIM}Select: ${C_RESET}"
}

# ─── Entry Point ───────────────────────────────────────────────────────────────
main() {
    trap 'show_cursor; exit 0' INT TERM

    check_root

    while true; do
        if is_installed; then
            show_main_menu_installed
            read -r choice
            case "$choice" in
                1) menu_update ;;
                2) menu_stop ;;
                3) menu_start ;;
                4) menu_restart ;;
                5) menu_view_logs ;;
                6) menu_edit_env ;;
                7) menu_uninstall ;;
                0) show_cursor; exit 0 ;;
                *) sleep 0.3 ;;
            esac
        else
            show_main_menu_not_installed
            read -r choice
            case "$choice" in
                1) menu_fresh_install ;;
                0) show_cursor; exit 0 ;;
                *) sleep 0.3 ;;
            esac
        fi
    done
}

main "$@"
