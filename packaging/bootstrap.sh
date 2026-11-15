#!/bin/bash
# 安装 / 更新运行环境（Python + 依赖 + livecaption），由菜单栏 App 首次打开时调用：
#   /bin/bash bootstrap.sh <用户数据目录> <App 的 Resources 目录>
# 逐行输出 JSON 进度：stage / progress / done / error。
# 全部成功后才替换旧环境；失败时旧环境不受影响，再次运行会接着用已下载的文件。
set -uo pipefail
HOME_DIR="$1"; RES="$2"
# shellcheck disable=SC1091
source "$RES/runtime.lock"      # PY_TAR PY_SHA256 PY_BYTES PY_URLS WHEELS_BYTES RUNTIME_ID LC_WHEEL
RT="$HOME_DIR/pyenv"; NEW="$HOME_DIR/pyenv.new"; DL="$HOME_DIR/downloads"
PYPI_MIRRORS="https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple https://pypi.org/simple"
export PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_INPUT=1

json_str() { printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr '\n' ' '; }
stage() { printf '{"event":"stage","text":"%s"}\n' "$(json_str "$1")"; }
fail()  { printf '{"event":"error","error":"%s"}\n' "$(json_str "$1")"; exit 1; }
# 后台每 0.5 秒报告一次某个目录/文件已下载的字节数
watch_size() {  # $1=路径 $2=总字节 $3=已完成的基数
  while true; do
    local n; n=$(du -sk "$1" 2>/dev/null | cut -f1); n=$(( ${n:-0} * 1024 + $3 ))
    printf '{"event":"progress","done":%d,"total":%d}\n' "$n" "$2"; sleep 0.5
  done
}
# ⓪ 增量更新：Python 和依赖都没变（BASE_ID 相同），只换 livecaption 本身，几秒完成
if [ -f "$RT/.base-id" ] && [ "$(cat "$RT/.base-id")" = "$BASE_ID" ] && [ -x "$RT/python/bin/python3" ]; then
  stage "更新程序…"
  "$RT/python/bin/python3" -m pip install -q --no-deps --force-reinstall "$RES/$LC_WHEEL" 2>"$HOME_DIR/logs/bootstrap.err" \
    || fail "更新失败：$(tail -2 "$HOME_DIR/logs/bootstrap.err")"
  "$RT/python/bin/python3" -m compileall -q "$RT/python/lib/python3.13/site-packages/livecaption" >/dev/null 2>&1
  echo "$RUNTIME_ID" > "$RT/.runtime-id"
  printf '{"event":"done"}\n'; exit 0
fi

TOTAL=$(( PY_BYTES + WHEELS_BYTES ))
mkdir -p "$DL/wheels" "$HOME_DIR/logs"

# ① Python 运行时
if ! echo "$PY_SHA256  $DL/$PY_TAR" | shasum -a 256 -c - >/dev/null 2>&1; then
  stage "下载 Python 运行时…"
  watch_size "$DL/$PY_TAR.part" "$TOTAL" 0 & W=$!
  ok=0
  for u in $PY_URLS; do
    if curl -fsSL --retry 2 --connect-timeout 15 -C - -o "$DL/$PY_TAR.part" "$u"; then ok=1; break; fi
  done
  kill $W 2>/dev/null; wait $W 2>/dev/null
  [ $ok = 1 ] || fail "Python 运行时下载失败，请检查网络后重试"
  mv "$DL/$PY_TAR.part" "$DL/$PY_TAR"
  echo "$PY_SHA256  $DL/$PY_TAR" | shasum -a 256 -c - >/dev/null 2>&1 || { rm -f "$DL/$PY_TAR"; fail "Python 运行时校验失败，请重试"; }
fi
stage "解压 Python 运行时…"
rm -rf "$NEW"; mkdir -p "$NEW"
tar xzf "$DL/$PY_TAR" -C "$NEW" || fail "解压失败"
PY="$NEW/python/bin/python3"

# ② 下载依赖（国内镜像优先）。pip 每开始下一个文件会打印 “Downloading xxx.whl (5.1 MB)”，
#    据此按文件累加进度（共几十个文件，足够平滑）
stage "下载依赖（约 $(( WHEELS_BYTES / 1000000 )) MB）…"
ok=0
for m in $PYPI_MIRRORS; do
  set -o pipefail
  if "$PY" -m pip download --no-deps --only-binary=:all: -r "$RES/requirements.txt" -d "$DL/wheels" -i "$m" \
       --timeout 30 --progress-bar off 2>"$DL/pip.err" |
     awk -v base="$PY_BYTES" -v total="$TOTAL" '
       function emit(d) { if (d > total) d = total; printf "{\"event\":\"progress\",\"done\":%d,\"total\":%d}\n", d, total; fflush() }
       match($0, /\(([0-9.]+) (kB|MB|GB)\)$/) {
         s = substr($0, RSTART + 1, RLENGTH - 2); split(s, a, " ")
         mul = (a[2] == "kB") ? 1e3 : (a[2] == "MB") ? 1e6 : 1e9
         done += prev; prev = a[1] * mul; emit(base + done)
       }
       END { emit(base + done + prev) }'; then ok=1; break; fi
done
[ $ok = 1 ] || fail "依赖下载失败：$(tail -2 "$DL/pip.err")"
printf '{"event":"progress","done":%d,"total":%d}\n' "$TOTAL" "$TOTAL"

# ③ 安装（离线，从刚下载的文件）
stage "安装依赖…"
"$PY" -m pip install -q --no-deps --no-index --find-links "$DL/wheels" -r "$RES/requirements.txt" 2>"$DL/pip.err" \
  || fail "依赖安装失败：$(tail -2 "$DL/pip.err")"
"$PY" -m pip install -q --no-deps "$RES/$LC_WHEEL" 2>"$DL/pip.err" || fail "安装 livecaption 失败：$(tail -2 "$DL/pip.err")"
stage "优化启动速度…"
"$PY" -m compileall -q -j0 "$NEW/python/lib" >/dev/null 2>&1
"$PY" -I -c "import livecaption.main, livecaption.overlay, sherpa_onnx, mlx.core" 2>"$DL/pip.err" \
  || fail "运行环境自检失败：$(tail -2 "$DL/pip.err")"

# ④ 替换旧环境
echo "$RUNTIME_ID" > "$NEW/.runtime-id"
echo "$BASE_ID" > "$NEW/.base-id"
rm -rf "$RT" && mv "$NEW" "$RT"
rm -rf "$DL"
printf '{"event":"done"}\n'
