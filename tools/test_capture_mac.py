"""Mac 抓音实测：用 catap 抓系统声音（mute=True：抓取期间静音，测试时不出声），同时 afplay 播放一段样音，
抓到的声音经重采样后交给 SenseVoice 识别。用法（需在有录音权限的终端里跑）：python -I tools/test_capture_mac.py 输出目录"""
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

import catap
import numpy as np
import soundfile as sf

from livecaption import sysaudio
from livecaption.config import SR
from livecaption.resample import Resampler, to_mono_float

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
log = open(out / "result.txt", "w")
def p(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)

blocks, state = queue.Queue(), {}
def on_buffer(b):
    f = b.format
    if "rs" not in state:
        state["rs"] = Resampler(f.sample_rate); p(f"原始格式：{f.sample_rate} Hz，{f.num_channels} 声道，float={f.is_float}，{f.bits_per_sample} bit")
    blocks.put(state["rs"](to_mono_float(b.data, f.is_float, f.bits_per_sample, f.num_channels)))

stop = threading.Event()
sess = catap.record_system_audio(mono=True, mute=True, on_buffer=on_buffer)
sess.start(); t0 = time.time()
time.sleep(0.5)
subprocess.run(["afplay", "data/samples/yue.wav"])
time.sleep(1.0)
sess.close()
chunks = []
while not blocks.empty():
    chunks.append(blocks.get())
a = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
sf.write(out / "captured.wav", a, SR)
p(f"抓到 {len(a)/SR:.1f} 秒（实际用时 {time.time()-t0:.1f} 秒），峰值 {np.abs(a).max() if len(a) else 0:.3f}，全为零：{sess.captured_only_silence}")
import sherpa_onnx as so
d = "models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
r = so.OfflineRecognizer.from_sense_voice(model=f"{d}/model.int8.onnx", tokens=f"{d}/tokens.txt", use_itn=True)
s = r.create_stream(); s.accept_waveform(SR, a); r.decode_stream(s)
p("识别结果：", s.result.text)
