@echo off
chcp 65001 >nul
cd /d "%~dp0.."

rem ---- locate a working Python 3 interpreter ----
rem The Microsoft Store "python.exe" alias does nothing, so every candidate
rem must actually execute a tiny script before it is accepted.
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
  echo [ERROR] No working Python 3 found.
  echo         The "python" in this system may be the Microsoft Store
  echo         placeholder, which does nothing.
  echo.
  echo         Fix: install Python 3.8+ from
  echo             https://www.python.org/downloads/windows/
  echo         and tick "Add python.exe to PATH".
  echo         Or create python-path.txt in the repository root containing
  echo         the full path of a python.exe on one line.
  echo.
  pause
  exit /b 1
)

echo Using Python: %PYCMD%
echo Patching your installed Keil uVision 5.x to Simplified Chinese ...
echo (the original UV4.exe is backed up as UV4.exe.bak first)
echo (please CLOSE any running Keil / uVision first)
echo.
if not exist build mkdir build
%PYCMD% "build_patch.py" %* > "build\build.log" 2>&1
set "RC=%ERRORLEVEL%"
type "build\build.log"
echo.
if "%RC%"=="0" (
  echo [OK] Done. Your normal Keil shortcut now starts the Chinese UI.
  echo      The English original is kept as UV4.exe.bak next to UV4.exe.
  echo      To switch back to English, run the restore script.
) else (
  echo [FAILED] exit code %RC%.  Full log saved to: build\build.log
)
echo.
pause
exit /b %RC%

:probe
%~1 -c "print(1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=%~1"
exit /b 0
