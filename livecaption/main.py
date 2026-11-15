"""入口：组装 音频源 → Captioner（SenseVoice + 断句）→ Refiner（Qwen 精修 + 翻译）→ 悬浮窗"""
import signal
import sys
import threading
import time

from . import config
from .audio import file_source, stdin_source, system_source
from .bus import Bus
from .captioner import Captioner
from .refiner import Refiner
from .runtime import Runtime, watch_parent
from .sensevoice import SenseVoice
from .textproc import TextProcessor

EXIT_ALREADY_RUNNING = 3


def main(argv=None):
    cfg = config.load(argv)
    a = cfg.args
    live = not a.file
    rt = Runtime(cfg.paths.runtime)
    if live and not rt.acquire_lock():
        print("已有一个实时字幕在运行（同一时间只允许一个）", file=sys.stderr)
        sys.exit(EXIT_ALREADY_RUNNING)

    stop = threading.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: stop.set())
    if a.parent_pid:
        watch_parent(a.parent_pid, stop.set)

    bus = Bus(debug=a.debug, ui=not a.no_ui, log_dir=cfg.paths.logs if live else None)
    tp = TextProcessor(a.script, cfg.paths.hotwords)
    asr = SenseVoice(cfg.paths.sensevoice, a.lang, cfg.asr.threads, cfg.filt.token_rel_energy)
    refiner = Refiner(cfg, bus, tp)
    if a.fast and not a.file:
        sys.exit("--fast 只能和 --file 一起用")
    if a.file:
        source = file_source(a.file, stop, realtime=not a.fast)
    elif a.audio_stdin:
        source = stdin_source(stop)
    else:
        source = system_source(cfg.paths.audiotee, stop)
    cap = Captioner(cfg, bus, tp, asr, refiner, source, stop)

    refiner.start()
    threading.Thread(target=cap.run, daemon=True, name="captioner").start()

    if a.no_ui:
        while not stop.is_set():
            time.sleep(0.2)
        deadline = time.time() + (600 if a.fast else 60)        # 等精修/翻译把剩下的句子做完
        while refiner.enabled and not refiner.idle() and time.time() < deadline:
            time.sleep(0.2)
        time.sleep(0.5)
        return

    from .overlay import run_overlay
    run_overlay(bus, cfg.display, refiner.use_mt, stop, on_ready=rt.mark_ready)
