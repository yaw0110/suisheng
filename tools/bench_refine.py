"""对比“精修”引擎：同样的句子音频，不同的运行程序 / 模型。
用法：python -I tools/bench_refine.py <引擎> <输出.json> <音频目录或文件>...
引擎：mlx:<模型目录>   sherpa:<模型目录>[:线程数[:provider]]   llama:<服务地址>
"""
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from livecaption.textproc import TextProcessor

engine, out = sys.argv[1], sys.argv[2]
files = []
for a in sys.argv[3:]:
    p = Path(a)
    files += sorted(p.glob("*.wav")) if p.is_dir() else [p]
tp = TextProcessor("s", None)
kind, _, arg = engine.partition(":")
t0 = time.time()

if kind == "mlx":
    from mlx_audio.stt.utils import load_model
    m = load_model(arg)
    m.generate(np.zeros(16000, np.float32))

    def run(x):
        r = m.generate(x)
        lang = getattr(r, "language", None) or [None]
        return getattr(r, "text", "") or "", lang[0] if isinstance(lang, list) else lang
elif kind == "sherpa":
    import sherpa_onnx as so
    parts = arg.split(":")
    d = parts[0]; threads = int(parts[1]) if len(parts) > 1 else 4; provider = parts[2] if len(parts) > 2 else "cpu"
    rec = so.OfflineRecognizer.from_qwen3_asr(
        conv_frontend=f"{d}/conv_frontend.onnx", encoder=f"{d}/encoder.int8.onnx", decoder=f"{d}/decoder.int8.onnx",
        tokenizer=f"{d}/tokenizer", num_threads=threads, provider=provider)

    def run(x):
        s = rec.create_stream(); s.accept_waveform(16000, x); rec.decode_stream(s)
        return s.result.text, getattr(s.result, "lang", "") or None
    run(np.zeros(16000, np.float32))
elif kind == "llama":
    import base64, io, urllib.request

    def run(x):
        buf = io.BytesIO(); sf.write(buf, x, 16000, format="WAV", subtype="PCM_16")
        body = {"temperature": 0, "max_tokens": 200, "messages": [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": base64.b64encode(buf.getvalue()).decode(), "format": "wav"}}]}]}
        req = urllib.request.Request(arg + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        txt = json.load(urllib.request.urlopen(req, timeout=120))["choices"][0]["message"]["content"]
        lang = None
        if "<asr_text>" in txt:                       # Qwen3-ASR 原始输出：language Cantonese<asr_text>……
            head, txt = txt.split("<asr_text>", 1)
            lang = head.replace("language", "").strip() or None
        return txt, lang
    run(np.zeros(16000, np.float32))
else:
    sys.exit("未知引擎")

load = time.time() - t0
res, tot_audio, tot_time = {}, 0.0, 0.0
for f in files:
    x, sr = sf.read(f, dtype="float32")
    x = x if x.ndim == 1 else x.mean(1)
    assert sr == 16000, f
    t = time.time(); txt, lang = run(x); dt = time.time() - t
    key = f"{f.parent.name}/{f.stem}"
    res[key] = {"text": tp.tidy(txt), "raw": txt, "lang": lang, "audio": round(len(x) / 16000, 2), "secs": round(dt, 3)}
    tot_audio += len(x) / 16000; tot_time += dt
summary = {"engine": engine, "load_secs": round(load, 1), "n": len(files), "audio_secs": round(tot_audio, 1),
           "infer_secs": round(tot_time, 1), "rtf": round(tot_time / max(tot_audio, 1e-9), 3),
           "avg_per_sentence": round(tot_time / max(len(files), 1), 2),
           "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576)}
json.dump({"summary": summary, "results": res}, open(out, "w"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False))
