#!/bin/bash
# macOS 打包：PyInstaller → 放入 llama.cpp → ad-hoc 签名 → 校验 → DMG。用法：packaging/build_mac.sh [--no-test]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
PY="${PYTHON:-$ROOT/.venv-build/bin/python}"
LLAMA_BUILD="b12359"
CACHE="$HOME/Library/Caches/livecaption-build"
VER=$("$PY" -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
APP="dist/Suisheng.app"
step() { echo; echo "==> $*"; }

step "1/5 PyInstaller"
rm -rf build/pyi dist
"$PY" -m PyInstaller --noconfirm --clean --log-level WARN --distpath dist --workpath build/pyi packaging/suisheng.spec

step "2/5 放入 llama.cpp（$LLAMA_BUILD，只取 llama-server 及其依赖库）"
mkdir -p "$CACHE/llama"; T="$CACHE/llama/llama-$LLAMA_BUILD-bin-macos-arm64.tar.gz"
[ -f "$T" ] || curl -fSL --retry 3 ${HTTPS_PROXY:+--proxy "$HTTPS_PROXY"} -o "$T" \
   "https://github.com/ggml-org/llama.cpp/releases/download/$LLAMA_BUILD/llama-$LLAMA_BUILD-bin-macos-arm64.tar.gz"
X=$(mktemp -d); tar xzf "$T" -C "$X"; SRC=$(dirname "$(find "$X" -name llama-server -type f | head -1)")
L="$APP/Contents/Resources/llama"; mkdir -p "$L"
cp "$SRC/llama-server" "$SRC/LICENSE" "$L/"; cp -P "$SRC"/*.dylib "$L/" 2>/dev/null || true
# 符号链接的 dylib 展开成真实文件（复制到用户目录时不依赖链接）
for f in "$L"/*.dylib; do [ -L "$f" ] && cp --remove-destination "$(readlink -f "$f")" "$f" 2>/dev/null || { [ -L "$f" ] && t=$(readlink -f "$f") && rm "$f" && cp "$t" "$f"; } ; done
echo "$LLAMA_BUILD" > "$L/VERSION"; rm -rf "$X"
du -sh "$L"

step "3/5 签名（ad-hoc）"
for f in "$L"/llama-server "$L"/*.dylib; do codesign --force -s - "$f"; done
codesign --force -s - "$APP"
codesign --verify --deep --strict "$APP" && echo "签名校验通过"
find "$APP" -not -perm -004 -print | head -3          # 应为空：App 内文件都需对所有人可读

step "4/5 自检：用打包好的程序识别一段样音（精修走包内 llama.cpp）"
if [ "${1:-}" != "--no-test" ] && [ -f data/samples/yue.wav ]; then
  LIVECAPTION_HOME="$ROOT" "$APP/Contents/MacOS/Suisheng" --file data/samples/yue.wav --fast --no-ui 2>/dev/null
fi

step "5/5 DMG"
S=$(mktemp -d); cp -R "$APP" "$S/"; ln -s /Applications "$S/Applications"; cp packaging/INSTALL.txt "$S/"
DMG="dist/Suisheng-$VER-macos-arm64.dmg"
hdiutil create -quiet -volname "Suisheng $VER" -srcfolder "$S" -ov -format UDZO "$DMG"; rm -rf "$S"
echo; echo "完成：$DMG（$(du -h "$DMG" | cut -f1)），App $(du -sh "$APP" | cut -f1)"
