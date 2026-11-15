"""实时识别主循环：SenseVoice 每隔一小段时间对“未定稿的音频”整体重识别，
按字间停顿切出定稿句（交给精修线程），其余作为临时字幕。"""
import traceback

import numpy as np

from .bus import END, FINAL, PARTIAL
from .config import SR
from .segmenter import SegParams, plan_splits
from .textproc import meaningful


def _rms(x):
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


class Captioner:
    def __init__(self, cfg, bus, tp, asr, refiner, source, stop):
        self.bus, self.tp, self.asr, self.refiner = bus, tp, asr, refiner
        self.source, self.stop = source, stop
        self.seg = SegParams(**vars(cfg.seg))
        self.refresh0 = cfg.asr.refresh
        self.f = cfg.filt
        self.record = cfg.args.record
        self.fast = cfg.args.fast     # 可复现模式：用“已收到的音频时长”当时钟，刷新间隔固定
        self.sid = 0          # 定稿句编号：精修/翻译结果靠它对回屏幕上的句子
        self.pending = ""     # 当前临时字幕（静音时直接把它定稿）
        self.last = ""        # 上一句定稿（去重）

    def run(self):
        try:
            self._loop()
        except Exception:
            traceback.print_exc()
        finally:
            self.bus.put(END)
            self.stop.set()

    # ---- 输出 ----
    def _partial(self, raw):
        self.pending = raw
        text = self.tp.tidy(raw)
        if text and not meaningful(text):
            return
        self.bus.put(PARTIAL, text)

    def _final(self, raw, audio):
        self.pending = ""
        text = self.tp.tidy(raw)
        if text:
            self.bus.dbg(f"  [final   音频 {self.bus.fed/SR:5.1f}s 实际 {self.bus.now():5.1f}s] {text}")
        r = self.refiner
        if (r.use_qwen and audio is not None and len(audio) > SR * 0.4
                and _rms(audio) > self.f.min_audio_rms):
            self.sid += 1                                       # 交给 Qwen 精修；先显示 SenseVoice 版本
            r.submit(self.sid, audio.copy(), text if meaningful(text) else "")
            if meaningful(text):
                self.bus.put(FINAL, (self.sid, text))
            return
        if not text or not meaningful(text) or text == self.last:
            return
        self.last = text
        self.bus.caption(text)
        self.sid += 1
        if r.use_mt:
            r.submit(self.sid, None, text)
        self.bus.put(FINAL, (self.sid, text))

    # ---- 主循环 ----
    def _loop(self):
        buf = np.zeros(0, np.float32)
        last, refresh = 0.0, self.refresh0
        rec = None
        if self.record:
            import soundfile as sf
            rec = sf.SoundFile(self.record, "w", SR, 1, "PCM_16")
        import time
        clock = (lambda: self.bus.fed / SR) if self.fast else time.time
        for chunk in self.source:
            self.bus.fed += len(chunk)
            buf = np.concatenate([buf, chunk])
            if rec:
                rec.write(chunk); rec.flush()
            if clock() - last < refresh - 1e-6:
                continue
            last = clock()
            buflen = len(buf) / SR
            if _rms(buf[-int(SR * 1.5):]) < self.f.silence_rms and buflen > 1.5:
                # 近 1.5 秒静音：把残余临时字幕定稿后清空（不再对静音重识别，避免幻听）
                if self.pending:
                    self._final(self.pending, buf[:-int(SR * 1.2)] if len(buf) > SR * 1.6 else buf)
                self._partial("")
                buf = buf[-int(SR * 0.3):]
                continue
            t0 = time.time()
            toks = self.asr.decode(buf)
            if not self.fast:                                   # 自适应：识别慢就少刷几次，避免积压
                refresh = max(self.refresh0, 1.5 * (time.time() - t0))
            if not toks:
                if buflen > 3:
                    buf = buf[-SR:]
                continue
            pts = plan_splits(toks, buflen, self.seg)
            if pts:
                start, a0 = 0, 0
                for i, cut in pts:                              # 每个停顿一句，连同这句的音频交给精修
                    a1 = int(cut * SR)
                    self._final("".join(t.text for t in toks[start:i + 1]), buf[a0:a1])
                    start, a0 = i + 1, a1
                buf = buf[max(0, int(pts[-1][1] * SR)):]
                self._partial("".join(t.text for t in toks[start:]))
            else:
                self._partial("".join(t.text for t in toks))
