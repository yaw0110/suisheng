#!/bin/bash
# 开发版：编译菜单栏 App 并安装到 ~/Applications/随声.app（使用源码目录的 .venv），会重启正在运行的 App
set -e
cd "$(dirname "$0")"
A="build/随声.app"
rm -rf build && mkdir -p "$A/Contents/MacOS"
mkdir -p "$A/Contents/Resources" && cp Info.plist "$A/Contents/Info.plist" && cp icon/AppIcon.icns "$A/Contents/Resources/"
swiftc -O main.swift ModelWindow.swift Capture.swift $(find ../vendor/audiotee/Sources/AudioTeeCore -name '*.swift') \
  -o "$A/Contents/MacOS/LiveCaption"
codesign --force --deep -s - "$A"
pkill -x LiveCaption 2>/dev/null && sleep 1 || true
rm -rf ~/Applications/实时字幕.app ~/Applications/随声.app && cp -R "$A" ~/Applications/
open ~/Applications/随声.app
echo "已安装并启动（开发版）：~/Applications/随声.app"
