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
rem  NOTE: keep this file pure ASCII.
rem  cmd.exe reads .bat with the system ANSI codepage, so UTF-8 Chinese
rem  in here would be mis-parsed as commands. All Chinese output is
rem  produced by Python instead.
rem
rem  Why so many python candidates: this machine has no python.exe on
rem  PATH, so we locate WorkBuddy's bundled interpreter ourselves.
rem  generator.py only needs the standard library.
rem ============================================================

set "PYEXE="

rem --- 1. Interpreter bundled with WorkBuddy ---
if exist "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PYEXE=%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not defined PYEXE if exist "C:\Users\xielei\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PYEXE=C:\Users\xielei\.workbuddy\binaries\python\versions\3.13.12\python.exe"

rem --- 2. Isolated env (also fine, just used as a fallback here) ---
if not defined PYEXE if exist "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PYEXE=%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
if not defined PYEXE if exist "C:\Users\xielei\.workbuddy\binaries\python\envs\default\Scripts\python.exe" set "PYEXE=C:\Users\xielei\.workbuddy\binaries\python\envs\default\Scripts\python.exe"

rem --- 3. Whatever happens to be on PATH ---
if not defined PYEXE for /f "delims=" %%p in ('where python.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%p"
if not defined PYEXE for /f "delims=" %%p in ('where python3.exe 2^>nul') do if not defined PYEXE set "PYEXE=%%p"

rem --- 4. Common per-user install locations ---
for %%v in (313 312 311 310) do if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
for %%v in (313 312 311 310) do if not defined PYEXE if exist "C:\Users\xielei\AppData\Local\Programs\Python\Python%%v\python.exe" set "PYEXE=C:\Users\xielei\AppData\Local\Programs\Python\Python%%v\python.exe"

if not defined PYEXE goto :nopython

echo ============================================================
echo   Game Ops Data Loop
echo ============================================================
echo.

"%PYEXE%" "01_datagen\generator.py" %*
if errorlevel 1 (
  echo.
  echo  [FAILED] generator exited with an error.
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
