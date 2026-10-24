@echo off
chcp 936 >nul
cd /d "%~dp0.."

rem ---- 自动请求管理员权限（写入 Keil 安装目录可能需要） ----
fltmc >nul 2>&1
if errorlevel 1 (
  echo [i] 正在请求管理员权限，请在弹窗中点「是」……
  powershell -NoProfile -Command "try { Start-Process -FilePath '%~f0' -Verb RunAs } catch { Write-Host '[×] 未获得管理员权限（已取消）。可右键本 bat 选「以管理员身份运行」重试。' ; exit 1 }"
  if errorlevel 1 pause
  exit /b
)

rem ---- 探测可用的 Python 3（商店占位程序会被真实执行测试排除） ----
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
  echo [错误] 没有找到可用的 Python 3。
  echo        正常情况下仓库 tools\python\ 已内置便携版 Python，无需安装；
  echo        走到这里说明仓库解压不完整，请重新下载解压整个仓库再试。
  echo.
  pause
  exit /b 1
)

echo 使用 Python: %PYCMD%
echo 即将把已安装的 Keil uVision 5.x 原地汉化为简体中文 ……
echo （原版 UV4.exe 会先备份为 UV4.exe.bak；请先关闭正在运行的 Keil）
echo.
if not exist build mkdir build
%PYCMD% "build_patch.py" %* > "build\build.log" 2>&1
set "RC=%ERRORLEVEL%"
type "build\build.log"
echo.
if "%RC%"=="0" (
  echo [成功] 汉化完成。照常双击桌面/开始菜单的 Keil 图标即为中文界面。
  echo        英文原版保留在 UV4.exe 旁的 UV4.exe.bak，随时可还原英文。
  echo        想还原英文：双击根目录「一键还原英文.bat」。
) else (
  echo [失败] 退出码 %RC%。完整日志见 build\build.log
  echo        常见原因：Keil 正在运行（请关闭后重试）、权限不足（右键「以管理员身份运行」）。
)
echo.
pause
exit /b %RC%

:probe
%~1 -c "print(1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=%~1"
exit /b 0
