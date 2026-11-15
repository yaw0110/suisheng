"""精修 + 翻译线程：Qwen3-ASR 重新识别每句定稿，Hy-MT2 翻译。

两个 MLX 模型放在同一个线程里串行跑（MLX 多线程并发不安全）。
积压超过 max_backlog 句时跳过旧句（保留 SenseVoice 结果），保证延迟不越积越多。
"""
import queue
import sys
import threading
import time

import numpy as np

from .bus import REVISE, TRANS
from .config import SR
from .textproc import meaningful
from .translate import Translator, need_translate

QWEN_LANG = {"yue": "Cantonese", "zh": "Chinese", "en": "English"}
KEEP_LANGS = ("Chinese", "Cantonese", "English")


class Refiner:
    def __init__(self, cfg, bus, tp):
        a = cfg.args
        self.bus, self.tp = bus, tp
        self.qwen_path, self.mt_path = cfg.paths.qwen_asr, cfg.paths.translator
        self.use_qwen = not a.no_qwen and self.qwen_path.is_dir()
        self.use_mt = a.translate and self.mt_path.is_dir()
        self.enabled = self.use_qwen or self.use_mt
        self.lang_kw = {"language": QWEN_LANG[a.lang]} if a.lang in QWEN_LANG else {}
        self.max_backlog = float("inf") if a.fast else cfg.refine.max_backlog   # 可复现测试时不跳句
        self.mt_context = cfg.translate.context
        self.q = queue.Queue()
        self.busy = False

    def start(self):
        if self.enabled:
            threading.Thread(target=self._run, daemon=True, name="refiner").start()

    def submit(self, sid, audio, text):
        """audio=None 表示不精修只翻译"""
        self.q.put((sid, audio, text))

    def idle(self):
        return self.q.empty() and not self.busy

    # ---- 线程内 ----
    def _run(self):
        self.busy = True
        tr = Translator(self.mt_path, self.mt_context) if self.use_mt else None
        qm = None
        if self.use_qwen:
            from mlx_audio.stt.utils import load_model
            qm = load_model(str(self.qwen_path))
            qm.generate(np.zeros(SR, np.float32))               # 预热
        self.busy = False
        while True:
            sid, audio, text = self.q.get()
            self.busy = True
            try:
                if audio is None:
                    self._translate(tr, sid, text)
                elif self.q.qsize() >= self.max_backlog:        # 积压：跳过这句精修，保留原识别结果
                    self.bus.dbg(f"  [跳过    #{sid}] 积压 {self.q.qsize()} 句")
                    if text:
                        self.bus.caption(text)
                else:
                    self._refine(qm, tr, sid, audio)
            except Exception as e:
                print("精修/翻译出错:", e, file=sys.stderr)
            finally:
                self.busy = False

    def _refine(self, qm, tr, sid, audio):
        t0 = time.time()
        r = qm.generate(audio, **self.lang_kw)
        txt = getattr(r, "text", "") or ""
        lang = getattr(r, "language", None) or [None]
        lang = lang[0] if isinstance(lang, list) else lang
        if lang and lang not in KEEP_LANGS:
            txt = ""                                            # 杂音被认成马来语/日语等：丢掉
        self.bus.dbg(f"  [qwen耗时 #{sid}] 音频 {len(audio)/SR:.1f}s → {time.time()-t0:.2f}s, 排队 {self.q.qsize()}")
        txt = self.tp.tidy(txt) if txt.strip() else ""
        if not meaningful(txt):
            return                                              # Qwen 判为无语音：相信它，丢掉 SenseVoice 的幻听
        self.bus.dbg(f"  [qwen    #{sid} 实际时间 {self.bus.now():5.1f}s] {txt}")
        self.bus.caption(txt)
        self.bus.put(REVISE, (sid, txt))
        self._translate(tr, sid, txt, lang)

    def _translate(self, tr, sid, txt, lang=None):
        if tr is None or not need_translate(txt, lang):
            return
        t0 = time.time()
        zh = self.tp.tidy(tr(txt))
        if not meaningful(zh) or zh == txt:
            return
        self.bus.dbg(f"  [翻译    #{sid} {time.time()-t0:.2f}s 实际 {self.bus.now():5.1f}s] {zh}")
        self.bus.translation(zh)
        self.bus.put(TRANS, (sid, zh))
