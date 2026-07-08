#!/bin/zsh
# 双击启动办公助手（摩尚OA v2）桌面客户端
cd "$(dirname "$0")/backend"
exec .venv/bin/python desktop.py
