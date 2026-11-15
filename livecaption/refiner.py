"""精修 + 翻译线程：Qwen3-ASR 重新识别每句定稿，Hy-MT2 翻译。都经 llama.cpp（llama-server 子进程）运行，跨平台。

两个模型在同一个线程里串行调用（各自一个 llama-server 进程）；
积压超过 max_backlog 句时跳过旧句（保留 SenseVoice 结果），保证延迟不越积越多。
"""
import queue
import sys
import threading
import time

from .bus import REVISE, TRANS
from .config import SR
from .llama import LlamaServer, QwenASR, find_gguf, find_server
from .textproc import meaningful
from .translate import Translator, need_translate

KEEP_LANGS = ("Chinese", "Cantonese", "English")


class Refiner:
    def __init__(self, cfg, bus, tp):
        a = cfg.args
        self.cfg, self.bus, self.tp = cfg, bus, tp
        self.exe = find_server(cfg)
        self.q_model, self.q_mmproj = find_gguf(cfg.paths.qwen_asr)
        self.t_model, _ = find_gguf(cfg.paths.translator)
        self.use_qwen = not a.no_qwen and bool(self.exe and self.q_model and self.q_mmproj)
        self.use_mt = a.translate and bool(self.exe and self.t_model)
        self.enabled = self.use_qwen or self.use_mt
        if (not a.no_qwen or a.translate) and not self.exe:
            print("提示：没找到 llama-server，精修 / 翻译不可用", file=sys.stderr)
        self.max_backlog = float("inf") if a.fast else cfg.refine.max_backlog   # 可复现测试时不跳句
        self.q = queue.Queue()
        self.busy = False
        self.servers = []

    def start(self):
        if self.enabled:
            threading.Thread(target=self._run, daemon=True, name="refiner").start()

    def submit(self, sid, audio, text):
        """audio=None 表示不精修只翻译"""
        self.q.put((sid, audio, text))

    def idle(self):
        return self.q.empty() and not self.busy

    def stop(self):
        for s in self.servers:
            s.stop()

    # ---- 线程内 ----
    def _server(self, name, model, mmproj=None, ctx=2048):
        L = self.cfg.llama
        s = LlamaServer(self.exe, model, mmproj, name=name, ctx=ctx, gpu_layers=L.gpu_layers, threads=L.threads,
                        run_dir=self.cfg.paths.runtime, log_dir=self.cfg.paths.logs)
        self.servers.append(s)
        return s.start()

    def _run(self):
        self.busy = True
        asr = tr = None
        try:
            if self.use_qwen:
                asr = QwenASR(self._server("qwen-asr", self.q_model, self.q_mmproj, ctx=4096))
            if self.use_mt:
                tr = Translator(self._server("translator", self.t_model), self.cfg.translate.context)
        except Exception as e:                                   # noqa: BLE001
            print("精修/翻译启动失败：", e, file=sys.stderr)
            self.use_qwen = self.use_mt = False
        self.busy = False
        while True:
            sid, audio, text = self.q.get()
            self.busy = True
            try:
                if audio is None:
                    self._translate(tr, sid, text)
                elif asr is None:
                    if text:
                        self.bus.caption(text)
                elif self.q.qsize() >= self.max_backlog:         # 积压：跳过这句精修，保留原识别结果
                    self.bus.dbg(f"  [跳过    #{sid}] 积压 {self.q.qsize()} 句")
                    if text:
                        self.bus.caption(text)
                else:
                    self._refine(asr, tr, sid, audio)
            except Exception as e:                               # noqa: BLE001
                print("精修/翻译出错:", e, file=sys.stderr)
            finally:
                self.busy = False

    def _refine(self, asr, tr, sid, audio):
        t0 = time.time()
        txt, lang = asr.transcribe(audio)
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
