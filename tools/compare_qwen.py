import sys, time, numpy as np, soundfile as sf, sherpa_onnx as so
from mlx_audio.stt.utils import load_model
B = sys.argv[1]; files = sys.argv[2:]
D = f"{B}/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
sv = so.OfflineRecognizer.from_sense_voice(model=f"{D}/model.int8.onnx", tokens=f"{D}/tokens.txt", language="auto", use_itn=True)
t = time.time(); q = load_model(f"{B}/models/Qwen3-ASR-1.7B-8bit"); print(f"Qwen 加载 {time.time()-t:.1f}s")
import inspect; print("generate 参数:", inspect.signature(q.generate))
def qwen(x, **kw):
    sf.write("/tmp/_q.wav", x, 16000); r = q.generate("/tmp/_q.wav", **kw)
    return getattr(r, "text", r)
qwen(np.zeros(16000, np.float32))
HW = [l.strip() for l in open(f"{B}/hotwords.txt", encoding="utf-8") if l.strip() and not l.startswith("#")]
for f in files:
    a, sr = sf.read(f, dtype="float32"); a = a if a.ndim == 1 else a.mean(1)
    for i in range(0, len(a), 16000 * 6):                 # 每 6 秒一段，模拟一句一句定稿
        x = a[i:i + 16000 * 6]
        if np.sqrt(np.mean(x ** 2)) < 0.003: continue
        t = time.time(); s = sv.create_stream(); s.accept_waveform(16000, x); sv.decode_stream(s); t1 = time.time() - t
        t = time.time(); qt = qwen(x); t2 = time.time() - t
        t = time.time(); qy = qwen(x, hotwords=HW); t3 = time.time() - t
        print(f"\n[{f.split('/')[-1]} {i//16000}s]\n SenseVoice ({t1*1000:.0f}ms): {s.result.text}\n Qwen       ({t2*1000:.0f}ms): {qt}\n Qwen+热词  ({t3*1000:.0f}ms): {qy}")
