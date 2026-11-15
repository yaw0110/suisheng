"""运行时管理：单实例锁、就绪标记（给菜单栏 App 看）、父进程看门狗"""
import atexit
import fcntl
import os
import threading
import time
from pathlib import Path


class Runtime:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ready_file = self.dir / "ready"
        self._lock_fd = None

    def acquire_lock(self):
        """同一时间只允许一个实时字幕（避免两层字幕）。拿不到锁返回 False"""
        fd = open(self.dir / "caption.lock", "w")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fd.close()
            return False
        fd.write(str(os.getpid())); fd.flush()
        self._lock_fd = fd                                      # 进程退出时系统自动释放
        return True

    def mark_ready(self):
        self.ready_file.touch()
        atexit.register(self.clear_ready)

    def clear_ready(self):
        try:
            self.ready_file.unlink()
        except FileNotFoundError:
            pass


def watch_parent(ppid, on_dead, interval=1.0):
    """父进程（菜单栏 App）没了就调用 on_dead，避免留下关不掉的字幕"""
    direct = os.getppid() == ppid          # ppid 是直接父进程时，还能用“被过继”来判断（防 PID 复用）

    def loop():
        while True:
            time.sleep(interval)
            try:
                os.kill(ppid, 0)
            except ProcessLookupError:
                on_dead(); return
            if direct and os.getppid() != ppid:
                on_dead(); return
    threading.Thread(target=loop, daemon=True, name="parent-watch").start()
