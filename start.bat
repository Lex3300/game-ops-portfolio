@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  Game Ops Data Loop - one-click launcher
rem
rem  Usage:
rem    double-click                 -> incremental, append missing days
rem    start.bat --days 90          -> generate 90 days from start date
rem    start.bat --reset --days 90  -> wipe and rebuild
rem
rem  IMPORTANT: keep this file pure ASCII.
rem  cmd.exe reads .bat with the system ANSI codepage, so UTF-8 Chinese
rem  in here would be mis-parsed as commands. All Chinese output is
rem  produced by Python instead.
rem ============================================================

set PYEXE=python
where python >nul 2>nul
if not errorlevel 1 goto :found

set PYEXE="%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" goto :found

set PYEXE="%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" goto :found

set PYEXE="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" goto :found

echo.
echo  [ERROR] Python 3.10+ not found.
echo  Install Python from https://www.python.org/downloads/ and retry.
echo.
pause
exit /b 1

:found
echo ============================================================
echo   Game Ops Data Loop
echo ============================================================
echo.

%PYEXE% "01_datagen\generator.py" %*
if errorlevel 1 (
  echo.
  echo  [FAILED] generator exited with an error.
  pause
  exit /b 1
)

echo.
pause
