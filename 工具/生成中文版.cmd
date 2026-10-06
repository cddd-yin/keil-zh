@echo off
chcp 65001 >nul
cd /d "%~dp0.."

rem ---- locate a working Python 3 interpreter ----
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
  echo [ERROR] No working Python 3 found.
  echo         Your "python" may be the Microsoft Store placeholder, which does nothing.
  echo         Please install Python 3.8+ from:
  echo             https://www.python.org/downloads/windows/
  echo         and tick "Add python.exe to PATH" during setup.
  echo.
  echo         Alternative: create python-path.txt in this folder with the full
  echo         path of a python.exe on one line.
  echo.
  pause
  exit /b 1
)

echo Using Python: %PYCMD%
echo Building the Simplified Chinese copy of Keil uVision ...
echo (the original UV4.exe will NOT be modified)
echo.
%PYCMD% "tools\build_patch.py" %*
echo.
pause
