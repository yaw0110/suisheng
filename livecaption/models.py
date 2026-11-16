"""模型管理：查看状态 / 下载。

下载源（按顺序尝试）：魔搭 ModelScope（国内直连）→ hf-mirror → huggingface.co（自动沿用系统代理）。
文件清单、大小、sha256 固定在 model_manifest.json：不需要先联网查询；每个文件下完都校验 sha256。
用 macOS 自带的 curl 下载：断点续传；30 秒内速度低于 1KB/s 判定卡死，断开后接着下。

  python -m livecaption.models status   [--home H]          → 一行 JSON：各模型是否已安装
  python -m livecaption.models download NAME [--home H]     → 逐行 JSON 进度（给菜单栏 App 显示）
"""
import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .config import default_home, load_raw

MARK = ".complete"
MANIFEST = json.loads((Path(__file__).parent / "model_manifest.json").read_text(encoding="utf-8"))
# key 与 config.toml [models] 里的目录名对应
CATALOG = {
    "sensevoice": {"title": "实时识别（SenseVoice，必需）", "size_mb": 240},
    "qwen_asr": {"title": "Qwen 精修（粤语更准，可选）", "size_mb": 2530},
    "translator": {"title": "翻译（粤语/英文→普通话，可选）", "size_mb": 1130},
}
TRIES_PER_SOURCE = 3


def model_dir(home, key):
    raw = load_raw(home)
    return Path(home) / raw["models"]["dir"] / raw["models"][key]


def _files(key):
    return MANIFEST[key]["files"]              # [[相对路径, 字节数, sha256], ...]


def installed(home, key):
    d = model_dir(home, key)
    if (d / MARK).exists():
        return True
    return all((d / p).exists() and (d / p).stat().st_size == size for p, size, _ in _files(key))


def status(home):
    return {k: {"title": v["title"], "size_mb": v["size_mb"], "installed": installed(home, k)}
            for k, v in CATALOG.items()}


def _print(**kw):
    print(json.dumps(kw, ensure_ascii=False), flush=True)


_emit = _print


def _log(home, msg):
    """下载出错的详细原因记到 <home>/logs/download.log，方便排查"""
    try:
        p = Path(home) / "logs"; p.mkdir(parents=True, exist_ok=True)
        with open(p / "download.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def _url(src, path):
    if src["type"] == "modelscope":
        return f"https://www.modelscope.cn/models/{src['repo']}/resolve/master/{path}"
    return f"{src['endpoint']}/{src['repo']}/resolve/{src['revision']}/{path}"


def _proxy_args(src):
    """国内源直连；海外源沿用系统代理设置（curl 自己不读 macOS 的系统代理）"""
    if src["type"] == "modelscope" or "hf-mirror" in src.get("endpoint", ""):
        return ["--noproxy", "*"]
    p = urllib.request.getproxies().get("https")
    return ["--proxy", p] if p else []


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download(home, key, emit=None, cancel=None):
    """emit(**事件)：进度回调（默认打印 JSON 行）；cancel：threading.Event，置位即中止"""
    global _emit
    _emit = emit or _print
    d = model_dir(home, key)
    d.mkdir(parents=True, exist_ok=True)
    files = _files(key)
    total = sum(size for _, size, _ in files)

    def done_bytes():
        n = 0
        for p, s, _ in files:
            f, part = d / p, d / (p + ".part")
            n += min(f.stat().st_size if f.exists() else (part.stat().st_size if part.exists() else 0), s)
        return n

    last_err = "未知错误"
    for path, size, sha in files:
        dst, part = d / path, d / (path + ".part")
        if dst.exists() and dst.stat().st_size == size:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        ok = False
        for src in MANIFEST[key]["sources"]:
            name = "魔搭" if src["type"] == "modelscope" else src["endpoint"].replace("https://", "")
            _emit(event="source", endpoint=name)
            for attempt in range(1, TRIES_PER_SOURCE + 1):
                cmd = ["curl.exe" if sys.platform == "win32" else "curl", "-fL", "-sS", "-C", "-", "--connect-timeout", "15",
                       "--speed-limit", "1024", "--speed-time", "30",     # 30 秒低于 1KB/s → 判定卡死，断开重试
                       "-o", str(part), *_proxy_args(src), _url(src, path)]
                p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                     encoding="utf-8", errors="replace",
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                while p.poll() is None:
                    time.sleep(0.5)
                    if cancel is not None and cancel.is_set():
                        p.terminate(); p.wait()
                        _emit(event="error", error="已取消（再点下载会接着下）")
                        return 1
                    _emit(event="progress", done=done_bytes(), total=total)
                err = (p.stderr.read() or "").strip()
                if p.returncode == 33 or (part.exists() and part.stat().st_size > size):
                    part.unlink(missing_ok=True)                  # 服务器不支持续传 / 文件不对：从头下
                if p.returncode == 0 and part.exists() and part.stat().st_size == size:
                    if not sha or _sha256(part) == sha:
                        part.rename(dst); ok = True; break
                    last_err = f"{path} 校验和不一致（来自 {name}）"
                    _log(home, f"{key} {last_err}，删除重下")
                    part.unlink(missing_ok=True)
                else:
                    last_err = f"{path} @ {name}: curl 退出码 {p.returncode} {err[-160:]}"
                    _log(home, f"{key} 第 {attempt} 次失败：{last_err}")
                if attempt < TRIES_PER_SOURCE:
                    _emit(event="reconnect", count=attempt)
                    time.sleep(2 * attempt)
            if ok:
                break
            _emit(event="retry", endpoint=name, error=last_err[:200])
        if not ok:
            _emit(event="error", error=last_err[:300])
            return 1
    (d / MARK).write_text(time.strftime("%Y-%m-%d %H:%M:%S"))
    _emit(event="progress", done=total, total=total)
    _emit(event="done", key=key)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="livecaption.models")
    ap.add_argument("cmd", choices=["status", "download"])
    ap.add_argument("key", nargs="?", choices=list(CATALOG))
    ap.add_argument("--home")
    a = ap.parse_args(argv)
    home = Path(a.home).expanduser() if a.home else default_home()
    if a.cmd == "status":
        print(json.dumps(status(home), ensure_ascii=False)); return 0
    if not a.key:
        ap.error("download 需要指定模型名")
    return download(home, a.key)


if __name__ == "__main__":
    sys.exit(main())
