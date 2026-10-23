#!/bin/bash
clear
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; PURPLE='\033[0;35m'; CYAN='\033[0;36m'; WHITE='\033[1;37m'; NC='\033[0m'
echo -e "${PURPLE}⚡ NRB TOOLS • Docker Runtime Installer ⚡${NC}"
if [ -f /etc/os-release ]; then . /etc/os-release; OS=$ID; else echo -e "${RED}Cannot detect OS.${NC}"; exit 1; fi
if [[ "$OS" != "ubuntu" && "$OS" != "debian" ]]; then echo -e "${RED}Unsupported OS: $OS${NC}"; exit 1; fi
while true; do
  clear
  echo -e "${PURPLE}╔══════════════════════════════════════════════════════╗${NC}"
  echo -e "${PURPLE}║${NC}             ${CYAN}NRB TOOLS • DOCKER${NC}                  ${PURPLE}║${NC}"
  echo -e "${PURPLE}╚══════════════════════════════════════════════════════╝${NC}"
  echo -e "  ${CYAN}1.${NC} NRB Panel V2"
  echo -e "  ${CYAN}2.${NC} Docker Engine + Compose"
  echo -e "  ${CYAN}3.${NC} Cloudflare Tunnel Setup"
  echo -e "  ${CYAN}4.${NC} Docker Status"
  echo -e "  ${RED}0.${NC} Exit"
  echo -ne "${YELLOW}➜${NC} Choose [0-4]: "; read -r choice
  case "$choice" in
    1) echo -e "${GREEN}Starting NRB Panel V2...${NC}"; python3 nrb.py; ;;
    2)
      echo -e "${GREEN}Installing Docker runtime...${NC}"
      apt-get update -y
      apt-get install -y docker.io docker-compose-plugin socat
      systemctl enable --now docker
      docker --version
      ;;
    3)
      apt-get update -y && apt-get install -y curl
      curl -fsSL https://pkg.cloudflare.com/cloudflare-public-v2.gpg | tee /usr/share/keyrings/cloudflare-public-v2.gpg >/dev/null
      echo 'deb [signed-by=/usr/share/keyrings/cloudflare-public-v2.gpg] https://pkg.cloudflare.com/cloudflared any main' > /etc/apt/sources.list.d/cloudflared.list
      apt-get update -y && apt-get install -y cloudflared
      read -r -p "Cloudflare Tunnel Token: " token
      [ -n "$token" ] && cloudflared service install "$token"
      ;;
    4) docker info || true; docker ps -a || true; ;;
    0) exit 0 ;;
    *) echo -e "${RED}Invalid choice.${NC}"; sleep 1 ;;
  esac
  echo; read -r -p "Press Enter to continue..." _
done
