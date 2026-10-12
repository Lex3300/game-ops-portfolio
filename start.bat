@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  游戏运营数据闭环系统 · 一键启动
rem  Usage:  double-click, or run  start.bat --days 180 --reset
rem  NOTE: keep messages ASCII-only; Chinese output comes from Python.
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
