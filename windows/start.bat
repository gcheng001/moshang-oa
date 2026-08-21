@echo off
rem MoshangOA launcher (repo layout: run install.bat once first; portable package layout: run directly)
chcp 65001 >nul
setlocal
title 办公助手
cd /d "%~dp0"

rem Auto-update: pull latest code from GitHub before starting (repo layout only)
if exist "%~dp0..\.git" (
  echo 正在检查更新...
  cd /d "%~dp0.."
  git pull --ff-only origin main >nul 2>&1
  if errorlevel 1 (
    echo [提示] 自动更新失败（可能无网络或本地有改动），使用当前版本启动
  )
  cd /d "%~dp0"
)

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
echo （关闭主窗口后仍会在系统托盘常驻；从托盘菜单“退出办公助手”才会停止）
"%PYEXE%" "%SCRIPT%"
if errorlevel 1 (
  echo.
  echo [出错] 启动失败，请把本窗口和 logs\moshang_win.log 截图发给管理员
  pause
  exit /b 1
)
exit /b 0
