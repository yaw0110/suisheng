"""字幕引擎：音频源 → Captioner（SenseVoice + 断句）→ Refiner（Qwen 精修 + 翻译，llama.cpp）。
界面（Qt）和命令行共用；可反复 start / stop。事件从 engine.bus.q 取。"""
import threading

from . import config
from .audio import file_source, stdin_source, system_source
from .bus import Bus
from .captioner import Captioner
from .refiner import Refiner
from .sensevoice import SenseVoice
from .sysaudio import system_audio
from .textproc import TextProcessor


class Engine:
    def __init__(self, cfg, ui=True):
        self.cfg, self.ui = cfg, ui
        self.stop_event = threading.Event()
        self.bus = self.refiner = self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def _source(self):
        a = self.cfg.args
        if a.file:
            return file_source(a.file, self.stop_event, realtime=not a.fast)
        if a.audio_stdin:
            return stdin_source(self.stop_event)
        if getattr(a, "audiotee", None):                         # 旧的命令行抓音方式（开发用）
            return system_source(self.cfg.paths.audiotee, self.stop_event)
        return system_audio(self.stop_event)

    def start(self):
        """在调用线程里加载模型（约 1~3 秒），然后在后台线程跑识别；精修/翻译在自己的线程里加载"""
        cfg, a = self.cfg, self.cfg.args
        self.stop_event.clear()
        self.bus = Bus(debug=a.debug, ui=self.ui, log_dir=None if a.file else cfg.paths.logs)
        tp = TextProcessor(a.script, cfg.paths.hotwords)
        asr = SenseVoice(cfg.paths.sensevoice, a.lang, cfg.asr.threads, cfg.filt.token_rel_energy)
        self.refiner = Refiner(cfg, self.bus, tp)
        cap = Captioner(cfg, self.bus, tp, asr, self.refiner, self._source(), self.stop_event)
        self.refiner.start()
        self.thread = threading.Thread(target=cap.run, daemon=True, name="captioner")
        self.thread.start()
        return self

    def stop(self, timeout=3):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout)
        if self.refiner:
            self.refiner.stop()
        self.thread = None


def make_config(**opts):
    """界面用：把设置项转成命令行参数再走同一套配置加载"""
    argv = []
    for k, v in opts.items():
        flag = "--" + k.replace("_", "-")
        if v is True:
            argv.append(flag)
        elif v not in (None, False, ""):
            argv += [flag, str(v)]
    return config.load(argv)
