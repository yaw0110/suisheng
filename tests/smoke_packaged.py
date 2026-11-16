"""打包后冒烟测试（CI 用，macOS / Windows 通用）：
下载实时识别模型和一段粤语样音 → 用打包好的程序（命令行模式）识别 → 检查输出；再检查包内 llama-server 能运行。
用法：python -I tests/smoke_packaged.py <打包程序路径> <包内 llama 目录>"""
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")
import os
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

exe, llama_dir = Path(sys.argv[1]), Path(sys.argv[2])
home = Path(tempfile.mkdtemp(prefix="suisheng-smoke-"))
ROOT = Path(__file__).resolve().parent.parent

print("== 下载实时识别模型", flush=True)
rc = subprocess.run([sys.executable, "-X", "utf8", "-I", "-m", "livecaption.models", "download", "sensevoice", "--home", str(home)],
                    cwd=ROOT, stdout=subprocess.DEVNULL).returncode
assert rc == 0, "模型下载失败"

print("== 下载粤语样音", flush=True)
wav = home / "yue.wav"
urllib.request.urlretrieve("https://huggingface.co/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/"
                           "resolve/main/test_wavs/yue.wav", wav)

print("== 用打包好的程序识别", flush=True)
env = dict(os.environ, LIVECAPTION_HOME=str(home), PYTHONIOENCODING="utf-8")
out = subprocess.run([str(exe), "--home", str(home), "--file", str(wav), "--fast", "--no-ui", "--no-qwen"],
                     capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=600)
print(out.stdout); print(out.stderr[-2000:], file=sys.stderr)
text = "".join(l.split(" ", 1)[-1] for l in out.stdout.splitlines())
assert any(ch in text for ch in "我哋字意思"), f"识别结果不对：{text!r}"

print("== 包内 llama-server", flush=True)
srv = llama_dir / ("llama-server.exe" if os.name == "nt" else "llama-server")
v = subprocess.run([str(srv), "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace")
print((v.stdout + v.stderr).strip()[-300:])
assert "version" in (v.stdout + v.stderr), "llama-server 无法运行"
print("冒烟测试通过 ✅")
