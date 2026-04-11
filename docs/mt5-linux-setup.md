# MT5 & MCP Server Setup Guide for Linux (Wine)

이 문서는 Linux Mint(및 Ubuntu 계열) 환경에서 물리적인 Windows PC 없이 **가상의 Windows 환경(Wine)**을 구축하고, 그 위에 **MetaTrader 5 (MT5)**와 **MT5 MCP 서버**를 띄워 AI 에이전트와 통신하는 전체 과정을 가이드합니다.

## 1. 사전 필수 사항: Wine HQ 설치

안정적인 호환성을 위해 배포판의 기본 Wine 대신 최신 WineHQ 버전을 먼저 설치해야 합니다.

```bash
# 1. 32비트 아키텍처 활성화 및 저장소 키 추가
sudo dpkg --add-architecture i386
wget -qO- https://dl.winehq.org/wine-builds/winehq.key | sudo apt-key add -

# 2. Linux Mint (Ubuntu 기반) 저장소 리스트 추가 (Ubuntu 22.04 기준 예시)
sudo apt-add-repository "deb https://dl.winehq.org/wine-builds/ubuntu/ jammy main"

# 3. Wine 업데이트 및 안정 버전 설치
sudo apt update
sudo apt install --install-recommends winehq-stable
```

## 2. MetaTrader 5 데스크탑 클라이언트 설치

Wine이 설치되었다면 MT5 설치 파일을 다운로드하여 실행합니다. (이 과정에서 그래픽 UI 창이 열리며 Windows 프로그램 설치하듯 "다음"을 눌러 설치를 완료합니다.)

```bash
# MT5 공식 설치파일 다운로드
wget "https://download.mql5.com/cdn/web/metaquotes.software.corp/mt5/mt5setup.exe"

# Wine으로 설치 진행 (UI가 뜹니다)
wine mt5setup.exe
```
> **[중요]** 설치 완료 후 MT5 데스크탑 창이 열리면, **[데모 계정 로그인]**을 수행하시고 `[도구] -> [옵션] -> [전문가 조언자(Expert Advisors)]` 탭에서 반드시 **"자동 매매 허용 (Allow algorithmic trading)"**을 체크해 주셔야 MCP 서버가 매매를 실행할 수 있습니다.

## 3. Windows용 파이썬 환경 구축 (Wine 내부)

MT5 API는 오직 "Windows 파이썬"에서만 동작합니다. 리눅스 네이티브 Python 환경과 절대 섞이지 않도록 **Wine 전용 Python**을 설치합니다.

```bash
# Windows x64 전용 파이썬 다운로드 (3.11.x 권장)
wget https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe

# Wine 상에서 파이썬 조용히(Quiet) 인스톨 (PATH 추가 옵션 포함)
wine python-3.11.8-amd64.exe /quiet InstallAllUsers=1 PrependPath=1

# 설치 완료 확인 (WINEPREFIX 내부에 파이썬이 잡히는지 버전 확인)
wine python --version
```

## 4. MT5 MCP 서버 동기화 및 구동

최신 `uv` 패키지 관리자를 통해 Python 패키지 의존성을 관리하는 `Qoyyuum/mcp-metatrader5-server` 구동 환경을 만듭니다.

```bash
# 1. 프로젝트를 담을 폴더 생성 후 레포지토리 클론
cd ~/Github/agentic-trader
git clone https://github.com/Qoyyuum/mcp-metatrader5-server.git
cd mcp-metatrader5-server

# 2. 클론받은 폴더 내에서 `pip`를 통해 MCP 서버와 MT5 라이브러리 설치
# (wine python 환경 안으로 패키지가 깔림)
wine python -m pip install -e .
wine python -m pip install MetaTrader5
```

## 5. 실행 및 테스트 통신

모든 준비가 완료되었다면 에이전트와 통신할 준비를 합니다.

1. 바탕화면 또는 터미널을 통해 **Wine에서 MT5 단말기가 백그라운드에 켜져 있는 상태**를 만듭니다.
2. 터미널을 새로 열고, 셋업한 mcp 서버를 아래 명령어로 기동합니다.
   ```bash
   # MT5 MCP 서버를 stdio (통신 모드) 로 실행 대기
   wine python -m src.mcp_mt5.main
   ```

이 콘솔이 열린 상태로 두면, Linux 로컬에서 작동하는 AI 에이전트(Antigravity 등)가 이 프로세스를 타겟팅하여 계정 정보 조회 및 매매를 곧바로 시작할 수 있습니다.
