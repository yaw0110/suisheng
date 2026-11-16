"""运行时管理：单实例锁、就绪标记、父进程看门狗、进程查询（macOS / Windows 通用）"""
import atexit
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

WIN = sys.platform == "win32"


def pid_alive(pid):
    """进程是否还在。注意：Windows 上 os.kill(pid, 0) 会直接结束进程，不能用来探测"""
    if WIN:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(0x1000, False, int(pid))          # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        k32.CloseHandle(h)
        return bool(ok) and code.value == 259                  # STILL_ACTIVE
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def pid_name(pid):
    """进程的可执行文件名（查不到返回空串），用来确认没认错进程"""
    try:
        if WIN:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 creationflags=subprocess.CREATE_NO_WINDOW).stdout
            return out.split(",")[0].strip('"') if out.startswith('"') else ""
        out = subprocess.run(["ps", "-p", str(int(pid)), "-o", "comm="], capture_output=True, text=True).stdout
        return os.path.basename(out.strip())
    except (OSError, ValueError):
        return ""


class Runtime:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ready_file = self.dir / "ready"
        self._lock_fd = None

    def acquire_lock(self):
        """同一时间只允许一个实时字幕（避免两层字幕）。拿不到锁返回 False；进程退出时系统自动释放"""
        fd = open(self.dir / "caption.lock", "a+")
        try:
            if WIN:
                import msvcrt
                fd.seek(0)
                msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fd.close()
            return False
        self._lock_fd = fd
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
    """父进程没了就调用 on_dead，避免留下关不掉的字幕（命令行 --parent-pid 用）"""
    direct = os.getppid() == ppid          # ppid 是直接父进程时，还能用“被过继”来判断（防 PID 复用）

    def loop():
        while True:
            time.sleep(interval)
            if not pid_alive(ppid) or (direct and not WIN and os.getppid() != ppid):
                on_dead(); return
    threading.Thread(target=loop, daemon=True, name="parent-watch").start()
