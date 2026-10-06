@echo off
chcp 65001 >nul
cd /d "%~dp0.."

set "PYCMD="
if exist "python-path.txt" for /f "usebackq delims=" %%i in ("python-path.txt") do if not defined PYCMD set "PYCMD=%%i"
if not defined PYCMD if defined PYTHON set "PYCMD=%PYTHON%"
if not defined PYCMD if exist "tools\python\python.exe" set "PYCMD=tools\python\python.exe"
if not defined PYCMD for /d %%P in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if not defined PYCMD if exist "%%~P\python.exe" set "PYCMD=%%~P\python.exe"
if not defined PYCMD for /d %%P in ("C:\Python3*") do if not defined PYCMD if exist "%%~P\python.exe" set "PYCMD=%%~P\python.exe"
if not defined PYCMD for /d %%P in ("C:\Program Files\Python3*") do if not defined PYCMD if exist "%%~P\python.exe" set "PYCMD=%%~P\python.exe"
if not defined PYCMD call :probe python
if not defined PYCMD call :probe "py -3"

if not defined PYCMD (
  echo.
  echo [ERROR] No working Python 3 found. See README for setup.
  echo.
  pause
  exit /b 1
)

echo Using Python: %PYCMD%
echo Preview: matching the dictionary against the installed UV4.exe ...
echo (no file will be written)
echo.
if not exist build mkdir build
%PYCMD% "build_patch.py" --dry-run %* > "build\preview.log" 2>&1
set "RC=%ERRORLEVEL%"
type "build\preview.log"
echo.
echo Full log saved to: build\preview.log
echo.
pause
exit /b %RC%

:probe
%~1 -c "print(1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=%~1"
exit /b 0
