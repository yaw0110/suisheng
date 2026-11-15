"""线程间消息 + 输出：识别/精修线程往这里发事件，悬浮窗从这里取；定稿和译文同时写字幕记录"""
import os
import queue
import time

FINAL, PARTIAL, REVISE, TRANS, END = "final", "partial", "revise", "trans", "end"


class Bus:
    def __init__(self, debug=False, ui=True, log_dir=None):
        self.q = queue.Queue()
        self.debug, self.ui = debug, ui
        self.t0 = time.time()
        self.fed = 0                     # 已收到的音频采样数（调试用）
        self.log = None
        if log_dir:                      # 字幕记录按天追加：logs/captions-YYYY-MM-DD.txt，latest.txt 指向当天
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, time.strftime("captions-%Y-%m-%d.txt"))
            self.log = open(path, "a", encoding="utf-8")
            self.log.write(time.strftime("\n===== %Y-%m-%d %H:%M:%S 开始 =====\n")); self.log.flush()
            latest = os.path.join(log_dir, "latest.txt")
            try:
                if os.path.islink(latest) or os.path.exists(latest):
                    os.remove(latest)
                os.symlink(os.path.basename(path), latest)
            except OSError:
                pass

    def put(self, kind, payload=None):
        if self.ui or kind == END:
            self.q.put((kind, payload))

    def now(self):
        return time.time() - self.t0

    def dbg(self, msg):
        if self.debug:
            print(msg, flush=True)

    def _out(self, line):
        if not self.debug:
            print(line, flush=True)
        if self.log:
            self.log.write(line + "\n"); self.log.flush()

    def caption(self, text):
        """一句定稿原文"""
        self._out(time.strftime("%H:%M:%S") + " " + text)

    def translation(self, text):
        self._out("         → " + text)
