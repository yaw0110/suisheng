import sys, time, glob, os, numpy as np, soundfile as sf, sherpa_onnx as so
M = sys.argv[1]; S = sys.argv[2]
sv = so.OfflineRecognizer.from_sense_voice(model=f"{M}/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx",
    tokens=f"{M}/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/tokens.txt", use_itn=True, num_threads=4)
P = f"{M}/sherpa-onnx-streaming-paraformer-trilingual-zh-cantonese-en"
pf = so.OnlineRecognizer.from_paraformer(encoder=f"{P}/encoder.int8.onnx", decoder=f"{P}/decoder.int8.onnx",
    tokens=f"{P}/tokens.txt", num_threads=4, enable_endpoint_detection=False)
for w in sorted(glob.glob(f"{S}/*.wav")):
    a, sr = sf.read(w, dtype="float32");  a = a if a.ndim == 1 else a[:,0]; dur = len(a)/sr
    ref = open(w[:-4]+".txt").read().strip() if os.path.exists(w[:-4]+".txt") else "(真人录音，无标准答案)"
    t=time.time(); s=sv.create_stream(); s.accept_waveform(sr,a); sv.decode_stream(s); t1=time.time()-t
    st=pf.create_stream(); t=time.time(); first=None; n=int(sr*0.1); comp=0
    for i in range(0,len(a),n):
        st.accept_waveform(sr,a[i:i+n]); c=time.time()
        while pf.is_ready(st): pf.decode_stream(st)
        comp+=time.time()-c
        if first is None and pf.get_result(st).strip(): first=(i+n)/sr
    st.accept_waveform(sr,np.zeros(int(sr*0.8),dtype=np.float32)); st.input_finished()
    while pf.is_ready(st): pf.decode_stream(st)
    print(f"\n## {os.path.basename(w)}  时长 {dur:.1f}s\n参考      : {ref}\nSenseVoice: {s.result.text}  [{t1*1000:.0f}ms, RTF {t1/dur:.3f}]")
    print(f"Paraformer流式: {pf.get_result(st)}  [计算 RTF {comp/dur:.3f}, 首字出现于音频第 {first}s]")
