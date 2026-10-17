@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  Build the dashboard data, then open the dashboard page.
rem
rem  Usage:
rem    double-click             -> rebuild data.js (if possible) + open page
rem    dashboard.bat --no-open  -> rebuild data.js only
rem    dashboard.bat --today 2026-10-16  -> rebuild as of a given date
rem
rem  NOTE: keep this file pure ASCII.
rem  cmd.exe reads .bat with the system ANSI codepage, so UTF-8
rem  Chinese characters in here would be mis-parsed as commands.
rem ============================================================

set "PYEXE="

rem --- 1. Isolated env shipped with WorkBuddy ---
if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PYEXE=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PYEXE if exist "C:\Users\xielei\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PYEXE=C:\Users\xielei\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

rem --- 2. Interpreter bundled with WorkBuddy ---
if not defined PYEXE if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PYEXE=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not defined PYEXE if exist "C:\Users\xielei\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PYEXE=C:\Users\xielei\.workbuddy\binaries\python\versions\3.13.12\python.exe"

rem --- 3. Whatever happens to be on PATH ---
if not defined PYEXE for /f "delims=" %%p in ('where python.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%p"
if not defined PYEXE for /f "delims=" %%p in ('where python3.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%p"

rem --- 4. Common per-user install locations ---
for %%v in (313 312 311 310) do if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
for %%v in (313 312 311 310) do if not defined PYEXE if exist "C:\Users\xielei\AppData\Local\Programs\Python\Python%%v\python.exe" set "PYEXE=C:\Users\xielei\AppData\Local\Programs\Python\Python%%v\python.exe"

set "DASH=02_dashboard\index.html"

echo ============================================================
echo   Dashboard
echo ============================================================
echo.

if not exist "data\game.db" (
  echo  [WARN] data\game.db not found - skipping data rebuild.
  echo         Run start.bat first to generate the virtual database.
  echo.
  goto :open
)

if not defined PYEXE (
  echo  [WARN] Python not found - skipping data rebuild.
  echo         The page will use the existing data.js.
  echo.
  goto :open
)

rem --- activity engine: library + schedule ledger (frozen items never change) ---
"%PYEXE%" "03_activity_agent\activity_engine.py" all
if errorlevel 1 (
  echo.
  echo  [WARN] Activity engine failed - the page will use the existing schedule.
  echo.
)

rem --- sentiment corpus: deterministic virtual posts for block 06 ---
"%PYEXE%" "06_sentiment\gen_sentiment.py"
if errorlevel 1 (
  echo.
  echo  [WARN] Sentiment corpus failed - block 06 will show stale data.
  echo.
)

"%PYEXE%" "02_dashboard\build_data.py"
if errorlevel 1 (
  echo.
  echo  [WARN] Data rebuild failed - the page will use the existing data.js.
  echo.
)

:open
if /i "%~1"=="--no-open" (
  echo  Done. Data rebuilt, service not started (--no-open).
  echo.
  pause
  exit /b 0
)

if not defined PYEXE (
  echo  [WARN] Python not found - opening the static page only.
  echo         Write buttons stay disabled without the local service.
  start "" "%DASH%"
  pause
  exit /b 0
)

rem --- local bridge: lets the page write Excel / publish / show git cmd ---
echo.
echo  Starting local service on 127.0.0.1:8765 ...
start "Config Console" "%PYEXE%" "02_dashboard\serve.py"
echo  A new window opens the dashboard at http://127.0.0.1:8765/
echo  Close that window to stop the service.
echo.
timeout /t 3 >nul
exit /b 0
