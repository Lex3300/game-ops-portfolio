@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ============================================================
rem  Export the virtual database (data\game.db) to CSV / Excel
rem
rem  Usage:
rem    double-click              -> export + open the workbook
rem    export.bat --csv-only     -> CSV only
rem    export.bat --list         -> list available datasets
rem
rem  NOTE: keep this file pure ASCII.
rem  cmd.exe reads .bat with the system ANSI codepage, so UTF-8
rem  Chinese characters in here would be mis-parsed as commands.
rem
rem  Why so many python candidates: this machine has no python.exe
rem  on PATH. We look for WorkBuddy's bundled interpreter first
rem  (the isolated env ships openpyxl, which the Excel sheet needs).
rem ============================================================

set "PYEXE="

rem --- 1. Isolated env that ships openpyxl (needed for the Excel sheet) ---
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

:search_done
if not defined PYEXE goto :nopython

echo ============================================================
echo   Export Data
echo ============================================================
echo.

rem Double-click (no arguments) -> export and pop the result open.
if "%~1"=="" (
  "%PYEXE%" "01_datagen\export_data.py" --open
) else (
  "%PYEXE%" "01_datagen\export_data.py" %*
)

if errorlevel 1 (
  echo.
  echo  [FAILED] export exited with an error.
  pause
  exit /b 1
)

echo.
pause
exit /b 0

:nopython
echo.
echo  [ERROR] Python 3.10+ not found.
echo.
echo  Looked in:
echo    - %%USERPROFILE%%\.workbuddy\binaries\python\...
echo    - python.exe / python3.exe on PATH
echo    - %%LOCALAPPDATA%%\Programs\Python\Python3xx
echo.
echo  Fix: install Python 3.10+ and tick "Add python.exe to PATH",
echo       or tell WorkBuddy where your python lives.
echo.
pause
exit /b 1
