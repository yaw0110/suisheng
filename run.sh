#!/bin/bash
# 命令行启动实时字幕（平时用菜单栏 App 即可）。参数见 ./run.sh --help
cd "$(dirname "$0")" && exec .venv/bin/python -I -m livecaption "$@"
