@echo off
chcp 936 >nul
cd /d "%~dp0.."

rem ---- 探测可用的 Python 3（预览不写文件，一般无需管理员） ----
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
echo 预览模式：把词库与已安装的 UV4.exe 做匹配检查（不写任何文件）……
echo.
if not exist build mkdir build
%PYCMD% "build_patch.py" --dry-run %* > "build\preview.log" 2>&1
set "RC=%ERRORLEVEL%"
type "build\preview.log"
echo.
echo 完整日志见 build\preview.log
echo.
pause
exit /b %RC%

:probe
%~1 -c "print(1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=%~1"
exit /b 0
