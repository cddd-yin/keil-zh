@echo off
chcp 65001 >nul
cd /d "%~dp0.."
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY (
  echo.
  echo [ERROR] Python 3 not found. Please install Python 3.8+ from
  echo         https://www.python.org/downloads/windows/
  echo.
  pause
  exit /b 1
)
echo Preview: matching the dictionary against the installed UV4.exe ...
echo (no file will be written)
echo.
%PY% "tools\build_patch.py" --dry-run %*
echo.
pause
