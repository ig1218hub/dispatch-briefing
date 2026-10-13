@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PORT=8000
if not "%~1"=="" set PORT=%~1

rem ---- cloudflared 준비 (PATH 또는 tools\cloudflared.exe, 없으면 다운로드) ----
set CF=
where cloudflared >nul 2>&1 && set CF=cloudflared
if not defined CF if exist "tools\cloudflared.exe" set CF=tools\cloudflared.exe
if not defined CF (
  echo [1/3] cloudflared 다운로드 중...
  if not exist tools mkdir tools
  curl -L --fail -o tools\cloudflared.exe https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe
  if errorlevel 1 (
    echo cloudflared 다운로드 실패. 직접 설치: winget install --id Cloudflare.cloudflared
    pause
    exit /b 1
  )
  set CF=tools\cloudflared.exe
)

rem ---- BE 서버 실행 (별도 창) ----
echo [2/3] BE 서버 시작: http://localhost:%PORT%
start "briefing-BE" cmd /k "set PYTHONIOENCODING=utf-8 && python server.py --port %PORT%"

rem 서버가 뜰 때까지 최대 30초 대기
set /a N=0
:wait
timeout /t 1 /nobreak >nul
curl -s http://127.0.0.1:%PORT%/api/health >nul 2>&1 && goto up
set /a N+=1
if %N% lss 30 goto wait
echo BE 서버가 응답하지 않습니다. briefing-BE 창의 오류를 확인하세요.
pause
exit /b 1

:up
echo [3/3] trycloudflare 터널 시작
echo.
echo  아래 로그의 https://xxxx.trycloudflare.com 주소를 FE의 "BE 연결"에 입력하세요.
echo  종료: Ctrl+C (BE 창은 따로 닫기)
echo.
"%CF%" tunnel --no-autoupdate --url http://localhost:%PORT%
endlocal
