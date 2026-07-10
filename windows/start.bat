@echo off
rem MoshangOA launcher (repo layout: run install.bat once first; portable package layout: run directly)
chcp 65001 >nul
setlocal
title 办公助手
cd /d "%~dp0"

if exist "%~dp0runtime\python.exe" (
  set "PYEXE=%~dp0runtime\python.exe"
  set "SCRIPT=%~dp0serve_win.py"
) else if exist "%~dp0python\python.exe" (
  set "PYEXE=%~dp0python\python.exe"
  set "SCRIPT=%~dp0app\backend\serve_win.py"
) else (
  echo [提示] 首次使用请先双击 install.bat 完成安装（只需一次）
  echo.
  pause
  exit /b 1
)

echo 正在启动办公助手，稍候会弹出应用窗口...
echo （本控制台可最小化，关闭应用窗口即完全退出）
"%PYEXE%" "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo [出错] 启动失败，请把本窗口和 logs\moshang_win.log 截图发给管理员
  pause
  exit /b 1
)
exit /b 0
