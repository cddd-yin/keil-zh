@echo off
chcp 936 >nul
cd /d "%~dp0.."

rem ---- 自动请求管理员权限（还原 Keil 安装目录里的 UV4.exe 可能需要） ----
fltmc >nul 2>&1
if errorlevel 1 (
  echo [i] 正在请求管理员权限，请在弹窗中点「是」……
  powershell -NoProfile -Command "try { Start-Process -FilePath '%~f0' -Verb RunAs } catch { Write-Host '[×] 未获得管理员权限（已取消）。可右键本 bat 选「以管理员身份运行」重试。' ; exit 1 }"
  if errorlevel 1 pause
  exit /b
)

rem ---- 探测可用的 Python 3 ----
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
  echo [错误] 没有找到可用的 Python 3。请确认仓库已完整解压（tools\python\ 内置便携版）。
  echo.
  pause
  exit /b 1
)

echo 使用 Python: %PYCMD%
echo 正在还原英文原版 Keil uVision（从 UV4.exe.bak 恢复）……
echo.
%PYCMD% "build_patch.py" --restore
echo.
echo [完成] 已还原英文。如需再次汉化，双击根目录「一键安装汉化.bat」。
echo.
pause
exit /b 0

:probe
%~1 -c "print(1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=%~1"
exit /b 0
