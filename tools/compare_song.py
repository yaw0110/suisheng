import sys, time, numpy as np, mlx_whisper, opencc, sherpa_onnx as so
B = sys.argv[1]; a = np.fromfile(f"{B}/data/samples/song.pcm", np.int16).astype(np.float32) / 32768
cc = opencc.OpenCC("s2hk"); print(f"录音 {len(a)/16000:.0f}s")
D = f"{B}/models/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
sv = so.OfflineRecognizer.from_sense_voice(model=f"{D}/model.int8.onnx", tokens=f"{D}/tokens.txt", language="yue", use_itn=True)
W = f"{B}/models/whisper-large-v3-turbo"
def svr(x):
    s = sv.create_stream(); s.accept_waveform(16000, x); sv.decode_stream(s); return cc.convert(s.result.text)
mlx_whisper.transcribe(a[:16000], path_or_hf_repo=W, language="yue")  # warmup
for L in (10, 6):
    print(f"\n===== 每 {L}s 一段（模拟实时） =====")
    for i in range(0, len(a), L * 16000):
        x = a[i:i + L * 16000]
        t = time.time(); s1 = svr(x); t1 = time.time() - t
        t = time.time(); r = mlx_whisper.transcribe(x, path_or_hf_repo=W, language="yue", condition_on_previous_text=False, temperature=0.0)
        t2 = time.time() - t
        print(f"[{i//16000:>2}s] SenseVoice({t1*1000:.0f}ms): {s1}\n      Whisper   ({t2*1000:.0f}ms): {cc.convert(r['text'].strip())}")
    if L == 10:
        t = time.time(); r = mlx_whisper.transcribe(a, path_or_hf_repo=W, language="yue")
        print(f"\n===== Whisper 整段 60s 一次识别（{time.time()-t:.1f}s）=====\n{cc.convert(r['text'])}")
