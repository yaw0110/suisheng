#!/bin/bash
# 一键打包：生成 dist/随声-<版本>.dmg
#
# App 包里只有一个可执行文件（菜单栏 App，已内置抓系统声音），其余都是文本/压缩包：
#   bootstrap.sh（首次打开时安装运行环境）、runtime.lock、requirements.txt、livecaption-*.whl、默认热词/配置
# 运行环境（独立 Python + 依赖）首次打开时由 App 从国内镜像下载到用户目录。这样做是因为
# 免费签名的 App 里如果自带 Python 等可执行文件，从网上下载后会被 macOS 单独拦截。
#
# 用法：packaging/package.sh [--no-selftest]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
SELFTEST=1; [ "${1:-}" = "--no-selftest" ] && SELFTEST=0

VER=$(python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
PY_VER="3.13.18"; PBS_TAG="20261026"
PY_TAR="cpython-${PY_VER}+${PBS_TAG}-aarch64-apple-darwin-install_only.tar.gz"
PY_URLS="https://registry.npmmirror.com/-/binary/python-build-standalone/${PBS_TAG}/${PY_TAR} https://github.com/astral-sh/python-build-standalone/releases/download/${PBS_TAG}/${PY_TAR}"
CACHE="$HOME/Library/Caches/livecaption-build"
NAME="随声"; BUNDLE_ID="com.livecaption.app"
DIST="$ROOT/dist"; APP="$DIST/$NAME.app"; RES="$APP/Contents/Resources"
step() { echo; echo "==> $*"; }

step "1/6 准备构建用 Python（与用户端相同的 ${PY_VER}）"
mkdir -p "$CACHE"
if [ ! -f "$CACHE/$PY_TAR" ]; then
  for u in $PY_URLS; do curl -fSL --max-time 600 -o "$CACHE/$PY_TAR.part" "$u" && mv "$CACHE/$PY_TAR.part" "$CACHE/$PY_TAR" && break; done
fi
BPY_DIR="$CACHE/build-python-$PY_VER"
[ -x "$BPY_DIR/python/bin/python3" ] || { rm -rf "$BPY_DIR"; mkdir -p "$BPY_DIR"; tar xzf "$CACHE/$PY_TAR" -C "$BPY_DIR"; }
BPY="$BPY_DIR/python/bin/python3"
PY_SHA256=$(shasum -a 256 "$CACHE/$PY_TAR" | cut -d' ' -f1)
PY_BYTES=$(stat -f%z "$CACHE/$PY_TAR")

step "2/6 统计依赖下载量 + 构建 livecaption wheel"
REQ_HASH=$(shasum -a 256 requirements.txt | cut -c1-12)
WHL_CACHE="$CACHE/wheels-$REQ_HASH"
if [ ! -f "$WHL_CACHE/.ok" ]; then
  rm -rf "$WHL_CACHE"; mkdir -p "$WHL_CACHE"
  "$BPY" -m pip download -q --disable-pip-version-check --no-deps --only-binary=:all: -r requirements.txt \
     -d "$WHL_CACHE" -i https://pypi.tuna.tsinghua.edu.cn/simple && touch "$WHL_CACHE/.ok"
fi
WHEELS_BYTES=$(find "$WHL_CACHE" -name '*.whl' -exec stat -f%z {} + | awk '{s+=$1} END {print s}')
rm -rf "$DIST"; mkdir -p "$APP/Contents/MacOS" "$RES"
"$BPY" -m pip wheel -q --disable-pip-version-check --no-deps -w "$DIST/wheel" . 
LC_WHEEL=$(basename "$(ls "$DIST"/wheel/livecaption-*.whl)")
cp "$DIST/wheel/$LC_WHEEL" "$RES/"
BASE_ID=$( (echo "$PY_SHA256"; cat requirements.txt) | shasum -a 256 | cut -c1-16)      # Python + 依赖
RUNTIME_ID=$( (echo "$BASE_ID"; shasum -a 256 "$RES/$LC_WHEEL" | cut -d' ' -f1) | shasum -a 256 | cut -c1-16)   # + 程序本身
cat > "$RES/runtime.lock" <<LOCK
# 由 package.sh 生成：本版本 App 需要的运行环境
PY_TAR="$PY_TAR"
PY_SHA256="$PY_SHA256"
PY_BYTES=$PY_BYTES
PY_URLS="$PY_URLS"
WHEELS_BYTES=$WHEELS_BYTES
LC_WHEEL="$LC_WHEEL"
BASE_ID="$BASE_ID"
RUNTIME_ID="$RUNTIME_ID"
LOCK
echo "运行环境：Python $(( PY_BYTES / 1000000 ))MB + 依赖 $(( WHEELS_BYTES / 1000000 ))MB，编号 $RUNTIME_ID"

step "3/6 编译菜单栏 App（含抓系统声音）"
swiftc -O app/main.swift app/ModelWindow.swift app/Capture.swift \
  $(find vendor/audiotee/Sources/AudioTeeCore -name '*.swift') -o "$APP/Contents/MacOS/LiveCaption"
cp packaging/bootstrap.sh requirements.txt "$RES/"; chmod -x "$RES/bootstrap.sh"
cp livecaption/default_hotwords.txt "$RES/hotwords.txt"; cp app/icon/AppIcon.icns "$RES/"
cp livecaption/default_config.toml "$RES/config.default.toml"
sed -e "s#<string>com.livecaption.app.dev</string>#<string>${BUNDLE_ID}</string>#" \
    -e "s#<key>CFBundleShortVersionString</key><string>[^<]*</string>#<key>CFBundleShortVersionString</key><string>${VER}</string>#" \
    -e "s#<key>CFBundleVersion</key><string>[^<]*</string>#<key>CFBundleVersion</key><string>${VER}</string>#" \
    app/Info.plist > "$APP/Contents/Info.plist"

step "4/6 签名（免费 ad-hoc）"
codesign --force -s - "$APP"
codesign --verify --strict "$APP" && echo "签名校验通过"
echo "App 包内可执行文件：$(find "$APP" -type f -perm -u+x | sed "s#$APP/##")"

step "5/6 自检：模拟用户首次安装（真实联网下载）→ 跑一段粤语样音"
if [ $SELFTEST = 1 ]; then
  T=$(mktemp -d "$CACHE/selftest.XXXX")
  /bin/bash "$RES/bootstrap.sh" "$T" "$RES" | grep -E '"(stage|done|error)"' | sed 's/^/    /'
  [ "$(cat "$T/pyenv/.runtime-id")" = "$RUNTIME_ID" ] || { echo "❌ 运行环境安装失败"; exit 1; }
  if [ -d models ] && [ -f data/samples/yue.wav ]; then
    ln -s "$ROOT/models" "$T/models"
    OUT=$("$T/pyenv/python/bin/python3" -I -B -m livecaption --home "$T" --file data/samples/yue.wav --fast --no-ui --no-qwen 2>/dev/null)
    echo "$OUT" | sed 's/^/    /'
    [ -n "$OUT" ] || { echo "❌ 识别无输出"; exit 1; }
  fi
  rm -rf "$T"; echo "自检通过 ✓"
else
  echo "（跳过）"
fi

step "6/6 生成 DMG"
STAGE="$DIST/dmg"; mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
cp packaging/安装说明.txt "$STAGE/安装说明.txt"
DMG="$DIST/${NAME}-${VER}.dmg"
hdiutil create -quiet -volname "${NAME} ${VER}" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
rm -rf "$STAGE" "$DIST/wheel"
echo; echo "完成：$DMG（$(du -h "$DMG" | cut -f1)）"
