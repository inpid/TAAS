@echo off
chcp 65001 >nul
cd /d "%~dp0"
title TAAS 로스팅

set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY where python >nul 2>nul && set PY=python
if not defined PY (
  echo.
  echo [TAAS] 파이썬이 없어요.
  echo   1. https://www.python.org/downloads/ 에서 Python 설치
  echo   2. 설치 첫 화면에서 "Add python.exe to PATH" 체크 꼭 하기
  echo   3. 설치 끝나면 이 파일을 다시 더블클릭
  echo.
  start https://www.python.org/downloads/
  pause
  exit /b
)

echo [TAAS] 시작합니다. 이 검은 창은 닫지 마세요 (닫으면 프로그램 꺼짐)
start "" http://localhost:8765
%PY% -m app.server %*
pause
