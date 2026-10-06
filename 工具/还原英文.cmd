@echo off
chcp 65001 >nul
cd /d "%~dp0.."

set "PYCMD="
if exist "python-path.txt" for /f "usebackq delims=" %%i in ("python-path.txt") do if not defined PYCMD set "PYCMD=%%i"
if not defined PYCMD if defined PYTHON set "PYCMD=%PYTHON%"
if not defined PYCMD if exist "tools\python\python.exe" set "PYCMD=tools\python\python.exe"
if not defined PYCMD (
  python --version >nul 2>nul
  if not errorlevel 1 set "PYCMD=python"
)
if not defined PYCMD (
  py -3 --version >nul 2>nul
  if not errorlevel 1 set "PYCMD=py -3"
)

if not defined PYCMD (
  echo.
  echo [ERROR] No working Python 3 found. See README for setup.
  echo.
  pause
  exit /b 1
)

echo Using Python: %PYCMD%
echo Restoring the official English Keil uVision ...
echo.
%PYCMD% "tools\restore.py"
echo.
pause
