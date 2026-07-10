@echo off
rem MoshangOA install: download embedded Python + deps (run once on Windows)
chcp 65001 >nul
setlocal EnableExtensions
title MoshangOA Install
cd /d "%~dp0"

set PY_VER=3.12.10
set CACHE=%~dp0cache
set RUNTIME=%~dp0runtime
set PYZIP=%CACHE%\python-%PY_VER%-embed-amd64.zip
set PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

echo ==============================================
echo   办公助手 Windows 安装程序（只需运行一次）
echo   步骤：下载内嵌 Python + 安装依赖，约 1-3 分钟
echo ==============================================
echo.

if exist "%RUNTIME%\python.exe" (
  echo [跳过] Python 运行时已存在（如需重装请先删除 runtime 文件夹）
  goto deps
)

if not exist "%CACHE%" mkdir "%CACHE%"

echo [1/3] 下载内嵌版 Python %PY_VER% ...
if exist "%PYZIP%" goto unzip
curl -fL --retry 2 -o "%PYZIP%" "https://mirrors.huaweicloud.com/python/%PY_VER%/python-%PY_VER%-embed-amd64.zip"
if not errorlevel 1 goto unzip
echo   华为云镜像失败，改用 npmmirror ...
curl -fL --retry 2 -o "%PYZIP%" "https://registry.npmmirror.com/-/binary/python/%PY_VER%/python-%PY_VER%-embed-amd64.zip"
if not errorlevel 1 goto unzip
echo   npmmirror 失败，改用 python.org 官方源 ...
curl -fL --retry 2 -o "%PYZIP%" "https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-embed-amd64.zip"
if errorlevel 1 (
  echo [失败] Python 下载失败，请检查网络后重新双击本文件
  goto fail
)

:unzip
echo [2/3] 解压 Python 运行时 ...
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
tar -xf "%PYZIP%" -C "%RUNTIME%"
if errorlevel 1 (
  echo [失败] 解压失败（需要 Windows 10 1803 以上，系统自带 tar 命令）
  goto fail
)
rem enable site-packages (embedded python disables it by default)
(
  echo python312.zip
  echo .
  echo Lib\site-packages
) > "%RUNTIME%\python312._pth"

:deps
echo [3/3] 安装后端依赖 ...
"%RUNTIME%\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 (
  echo   正在引导 pip ...
  curl -fL --retry 2 -o "%CACHE%\get-pip.py" "https://bootstrap.pypa.io/get-pip.py"
  if errorlevel 1 curl -fL --retry 2 -o "%CACHE%\get-pip.py" "https://mirrors.aliyun.com/pypi/get-pip.py"
  if not exist "%CACHE%\get-pip.py" (
    echo [失败] get-pip.py 下载失败，请检查网络后重试
    goto fail
  )
  "%RUNTIME%\python.exe" "%CACHE%\get-pip.py" -i %PIP_MIRROR% --no-warn-script-location
  if errorlevel 1 (
    echo [失败] pip 安装失败
    goto fail
  )
)
"%RUNTIME%\python.exe" -m pip install --no-warn-script-location -i %PIP_MIRROR% "fastapi==0.139.0" "uvicorn==0.50.2" "requests==2.34.2" "colorama"
if errorlevel 1 (
  echo   清华镜像安装失败，改用官方 PyPI 重试 ...
  "%RUNTIME%\python.exe" -m pip install --no-warn-script-location "fastapi==0.139.0" "uvicorn==0.50.2" "requests==2.34.2" "colorama"
  if errorlevel 1 (
    echo [失败] 依赖安装失败，请把本窗口截图发给管理员
    goto fail
  )
)

"%RUNTIME%\python.exe" -c "import fastapi, uvicorn, requests" >nul 2>&1
if errorlevel 1 (
  echo [失败] 依赖自检未通过，请把本窗口截图发给管理员
  goto fail
)

echo.
echo ==============================================
echo   [完成] 安装成功！
echo   以后每次使用：双击 start.bat 启动办公助手
echo ==============================================
echo.
pause
exit /b 0

:fail
echo.
pause
exit /b 1
