"""llama.cpp 封装（跨平台）：用 llama-server 子进程跑 GGUF 模型，走本机 HTTP。
精修（Qwen3-ASR，音频输入）和翻译（Hy-MT2，文本）都用它；硬件加速（Metal / CUDA / Vulkan / CPU）由 llama.cpp 自己决定。
"""
import atexit
import base64
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

import numpy as np

from .config import SR

EXE = "llama-server.exe" if os.name == "nt" else "llama-server"
_NO_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))   # 本机请求不走系统代理


def bundled_dir():
    """安装包自带的 llama.cpp（打包时放在 App 里的 llama/ 目录）"""
    if not getattr(sys, "frozen", False):
        return None
    base = Path(sys.executable).resolve().parent                   # macOS: Contents/MacOS；Windows: 程序目录
    for d in (base / "llama", base.parent / "Resources" / "llama", base / "_internal" / "llama"):
        if (d / EXE).is_file():
            return d
    return None


def _install_mac_copy(src, home):
    """macOS：首次运行时把 App 内置的 llama.cpp 复制到用户数据目录，之后从那里启动。
    实测（macOS 15）：用户对 App 点过“仍要打开”后，由它写出的文件虽仍带来源标记，但已随 App 一并放行，可正常运行；
    同时用户数据目录可写，避免依赖 App 包内路径（App 被系统临时搬到只读位置运行时也不受影响）。"""
    version = (src / "VERSION").read_text(encoding="utf-8").strip() if (src / "VERSION").exists() else "llama"
    dst = Path(home) / "bin" / version
    if (dst / EXE).is_file() and (dst / ".ok").exists():
        return dst
    tmp = dst.with_name(dst.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copyfile(f, tmp / f.name)                       # copyfile：不复制扩展属性
            os.chmod(tmp / f.name, 0o755 if (f.name == EXE or f.suffix == ".dylib") else 0o644)
    (tmp / ".ok").write_text(version, encoding="utf-8")
    shutil.rmtree(dst, ignore_errors=True); tmp.rename(dst)
    return dst


def find_server(cfg):
    """llama-server 的位置：配置指定 → 安装包自带 → 系统里装的（开发用）"""
    custom = getattr(cfg.llama, "server", "") or None
    if custom and Path(custom).is_file():
        return str(custom)
    b = bundled_dir()
    if b is not None:
        if sys.platform == "darwin":
            try:
                b = _install_mac_copy(b, cfg.home)
            except OSError as e:
                log_err(f"复制 llama.cpp 失败：{e}")
        return str(b / EXE)
    for c in (shutil.which("llama-server"), "/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"):
        if c and Path(c).is_file():
            return str(c)
    return None


def find_gguf(model_dir):
    """模型目录里的主模型和（可选的）多模态投影文件：返回 (model, mmproj)；没有则 (None, None)"""
    d = Path(model_dir)
    if not d.is_dir():
        return None, None
    ggufs = sorted(p for p in d.glob("*.gguf"))
    mm = [p for p in ggufs if p.name.lower().startswith("mmproj")]
    main = [p for p in ggufs if p not in mm]
    return (main[0] if main else None), (mm[0] if mm else None)


def wav_bytes(x):
    """float32 单声道 → 16k/16bit WAV（内存里）"""
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm)
    return buf.getvalue()


class LlamaServer:
    def __init__(self, exe, model, mmproj=None, name="llama", ctx=2048, gpu_layers=99, threads=0, run_dir=None, log_dir=None):
        self.exe, self.model, self.mmproj, self.name = exe, Path(model), mmproj, name
        self.ctx, self.gpu_layers, self.threads = ctx, gpu_layers, threads
        self.run_dir = Path(run_dir) if run_dir else None
        self.log_dir = Path(log_dir) if log_dir else None
        self.proc, self.port = None, None

    # ---- 生命周期 ----
    def _kill_stale(self):
        """上次异常退出留下的同名 llama-server：按 pid 文件清掉（先确认那个进程确实是 llama-server，防止误杀）"""
        if not self.run_dir:
            return
        from .runtime import pid_alive, pid_name
        pf = self.run_dir / f"{self.name}.pid"
        try:
            pid = int(pf.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if pid_alive(pid) and pid_name(pid).lower().startswith("llama-server"):
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    os.kill(pid, 15)
            except OSError:
                pass

    def start(self, timeout=180):
        self._kill_stale()
        with socket.socket() as s:                              # 让系统挑一个空闲端口
            s.bind(("127.0.0.1", 0)); self.port = s.getsockname()[1]
        cmd = [self.exe, "-m", str(self.model), "--host", "127.0.0.1", "--port", str(self.port),
               "-c", str(self.ctx), "-ngl", str(self.gpu_layers), "--no-webui", "--parallel", "1"]
        if self.mmproj:
            cmd += ["--mmproj", str(self.mmproj)]
        if self.threads:
            cmd += ["-t", str(self.threads)]
        log = subprocess.DEVNULL
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log = open(self.log_dir / f"{self.name}.log", "w", encoding="utf-8")
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=flags)
        if self.run_dir:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            (self.run_dir / f"{self.name}.pid").write_text(str(self.proc.pid), encoding="utf-8")
        atexit.register(self.stop)
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server（{self.name}）启动失败，退出码 {self.proc.returncode}")
            try:
                with _NO_PROXY.open(f"http://127.0.0.1:{self.port}/health", timeout=2) as r:
                    if json.load(r).get("status") == "ok":
                        return self
            except Exception:                                    # noqa: BLE001  还在加载模型
                time.sleep(0.2)
        self.stop()
        raise TimeoutError(f"llama-server（{self.name}）{timeout} 秒内没有就绪")

    def stop(self):
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()
        if self.run_dir:
            try:
                (self.run_dir / f"{self.name}.pid").unlink()
            except OSError:
                pass

    # ---- 调用 ----
    def chat(self, content, max_tokens=200, timeout=120):
        """content：字符串，或 OpenAI 格式的内容块列表（可含 input_audio）"""
        body = {"temperature": 0, "max_tokens": max_tokens, "messages": [{"role": "user", "content": content}]}
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/v1/chat/completions", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with _NO_PROXY.open(req, timeout=timeout) as r:
            return json.load(r)["choices"][0]["message"]["content"]


class QwenASR:
    """Qwen3-ASR：输出形如 `language Cantonese<asr_text>文字`"""
    def __init__(self, server):
        self.server = server
        self.transcribe(np.zeros(SR, np.float32))               # 预热

    def transcribe(self, audio):
        """返回 (文字, 语种)。语种如 Chinese / Cantonese / English；判为无语音时文字为空"""
        b64 = base64.b64encode(wav_bytes(audio)).decode()
        out = self.server.chat([{"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}}])
        lang = None
        if "<asr_text>" in out:
            head, out = out.split("<asr_text>", 1)
            lang = head.replace("language", "").strip() or None
        if lang in (None, "None"):
            return "", None
        return out.strip(), lang


def log_err(msg):
    print(msg, file=sys.stderr, flush=True)
