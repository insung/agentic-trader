#!/bin/bash
# MT5 & Wine Python Environment Auto-Setup Script for Linux Mint/Ubuntu
# 주의: 이 스크립트는 sudo 권한을 요구하며, 중간중간 Wine 패키지 다운로드 및 그래픽 창이 뜰 수 있습니다.

echo "=========================================================="
echo " Starting MT5 + MCP (Wine) Environment Setup Script       "
echo "=========================================================="

echo "[1/4] Configuring 32-bit architecture & Adding WineHQ repo..."
sudo dpkg --add-architecture i386
sudo mkdir -pm755 /etc/apt/keyrings
sudo wget -O /etc/apt/keyrings/winehq-archive.key https://dl.winehq.org/wine-builds/winehq.key

# 보통 Linux Mint는 Ubuntu 버전을 기반으로 합니다. (Mint 21 = Ubuntu 22.04 Jammy 기준 설치)
# 주의: 만약 다른 버전이라면 저장소 주소를 수정해야 할 수 있습니다. 
sudo wget -NP /etc/apt/sources.list.d/ https://dl.winehq.org/wine-builds/ubuntu/dists/jammy/winehq-jammy.sources

echo "[2/4] Installing WineHQ Stable..."
sudo apt update
sudo apt install --install-recommends winehq-stable -y

echo "[3/4] Downloading MT5 and Windows Python (3.11.8)..."
mkdir -p ~/mt5_installer_temp
cd ~/mt5_installer_temp

if [ ! -f "mt5setup.exe" ]; then
    wget "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe" -O mt5setup.exe
fi

if [ ! -f "python-3.11.8-amd64.exe" ]; then
    wget "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe" -O python-3.11.8-amd64.exe
fi

echo "[4/4] Starting GUI Installers via Wine..."
echo "----------------------------------------------------------"
echo "[ACTION REQUIRED] 곧 Python 3.11 설치가 백그라운드에서 진행되며,"
echo "뒤이어 MT5 메타트레이더 창이 뜹니다. 마우스로 '다음'을 눌러 설치를 완료해주세요."
echo "----------------------------------------------------------"

# 파이썬 조용히 설치 (PATH 자동 추가)
wine python-3.11.8-amd64.exe /quiet InstallAllUsers=1 PrependPath=1

# MT5 그래픽 설치 런칭
wine mt5setup.exe

echo "=========================================================="
echo "설치가 완료되었다면 docs/mt5-linux-setup.md를 읽고 계정 로그인과 MCP 설정을 진행하세요."
echo "=========================================================="
