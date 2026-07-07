#!/bin/zsh
# 双击启动摩尚OA桌面客户端
cd "$(dirname "$0")/backend"
exec .venv/bin/python desktop.py
