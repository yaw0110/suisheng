"""SenseVoice（sherpa-onnx）：快速识别 + 逐字时间戳，并过滤静音处的幻听字"""
import numpy as np
import sherpa_onnx as so

from .config import SR
from .segmenter import Token

PUNCT = set("。，、？！；：,.?!;:…")
P_FINAL = set("。？！.?!…")


class SenseVoice:
    def __init__(self, model_dir, lang="auto", threads=4, token_rel_energy=0.12):
        self.rec = so.OfflineRecognizer.from_sense_voice(
            model=f"{model_dir}/model.int8.onnx", tokens=f"{model_dir}/tokens.txt",
            language=lang, use_itn=True, num_threads=threads)
        self.rel = token_rel_energy

    def decode(self, x):
        """识别一段音频，返回 [Token]，标点并入前一个字"""
        s = self.rec.create_stream()
        s.accept_waveform(SR, x)
        self.rec.decode_stream(s)
        fr = int(SR * 0.05)
        nf = max(1, len(x) // fr)
        rms = np.sqrt(np.mean(x[:nf * fr].reshape(nf, fr) ** 2, axis=1) + 1e-12)
        ref = float(np.percentile(rms, 90))
        out = []
        for t, ts in zip(s.result.tokens, s.result.timestamps):
            t0 = t.strip()
            if t0 == "":
                continue
            if t0 in PUNCT:
                if out:
                    last = out[-1]
                    out[-1] = Token(last.text + t0, last.ts, max(last.punct, 2 if t0 in P_FINAL else 1))
                continue
            a = int(ts / 0.05)                                  # 该字起点后 0.3 秒的音量
            if ref < 0.003 or rms[a:a + 6].max(initial=0) < self.rel * ref:
                continue                                        # 几乎没声音的位置冒出来的字 = 幻听
            out.append(Token(t, ts, 0))
        return out
