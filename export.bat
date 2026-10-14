@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  Export the virtual database to CSV / Excel
rem
rem  Usage:
rem    double-click              -> export to data\export (CSV + Excel)
rem    export.bat --csv-only     -> CSV only
rem    export.bat --list         -> list available datasets
rem
rem  IMPORTANT: keep this file pure ASCII.
rem  cmd.exe reads .bat with the system ANSI codepage, so UTF-8
rem  Chinese in here would be mis-parsed as commands.
rem ============================================================

rem Prefer an interpreter that already ships openpyxl, so the
rem Excel workbook can be generated. Falls back to plain CSV otherwise.
set PYEXE="%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" goto :found

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
echo.
pause
exit /b 1

:found
echo ============================================================
echo   Export Data
echo ============================================================
echo.

%PYEXE% "01_datagen\export_data.py" %*
if errorlevel 1 (
  echo.
  echo  [FAILED] export exited with an error.
  pause
  exit /b 1
)

rem Only pop the folder when launched with a double-click (no arguments),
rem so scripted calls stay silent.
if "%~1"=="" (
  echo.
  echo  Opening output folder...
  start "" "data\export"
)

echo.
pause
