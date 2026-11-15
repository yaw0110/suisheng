"""命令行入口（开发 / 测试用）：python -m livecaption [--file x.wav --no-ui ...]
不带 --no-ui 时打开图形界面（托盘 + 悬浮字幕），等同于 python -m livecaption.app"""
import signal
import sys
import time

from . import config
from .engine import Engine
from .runtime import Runtime, watch_parent

EXIT_ALREADY_RUNNING = 3


def main(argv=None):
    cfg = config.load(argv)
    a = cfg.args
    if not a.no_ui:
        from .ui.app import run_app
        return run_app(cfg)
    if a.fast and not a.file:
        sys.exit("--fast 只能和 --file 一起用")
    live = not a.file
    rt = Runtime(cfg.paths.runtime)
    if live and not rt.acquire_lock():
        print("已有一个实时字幕在运行（同一时间只允许一个）", file=sys.stderr)
        sys.exit(EXIT_ALREADY_RUNNING)
    eng = Engine(cfg, ui=False)
    for s in (signal.SIGINT, signal.SIGTERM):
        signal.signal(s, lambda *_: eng.stop_event.set())
    if a.parent_pid:
        watch_parent(a.parent_pid, eng.stop_event.set)
    eng.start()
    while not eng.stop_event.is_set():
        time.sleep(0.2)
    deadline = time.time() + (600 if a.fast else 60)            # 等精修/翻译把剩下的句子做完
    while eng.refiner.enabled and not eng.refiner.idle() and time.time() < deadline:
        time.sleep(0.2)
    time.sleep(0.5)
    eng.refiner.stop()
