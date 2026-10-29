#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "[TAAS] 파이썬이 없어요. 설치 창이 뜨면 '설치'를 누르고, 끝나면 이 파일을 다시 더블클릭하세요."
  xcode-select --install 2>/dev/null || open "https://www.python.org/downloads/"
  read -n 1 -s -r -p "아무 키나 누르면 닫혀요"
  exit 1
fi
echo "[TAAS] 시작합니다. 이 창은 닫지 마세요 (닫으면 프로그램 꺼짐)"
(sleep 2; open "http://localhost:8765") &
python3 -m app.server "$@"
