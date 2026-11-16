"""模型管理窗口：显示各模型是否已安装，下载（带进度、可取消、断点续传）"""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget)

from .. import models
from ..llama import find_server


class _Bridge(QObject):
    event = Signal(str, dict)            # 下载线程 → 界面线程
    finished = Signal(str, int)


class ModelsWindow(QWidget):
    changed = Signal()                   # 安装状态有变化（菜单要刷新）

    def __init__(self, cfg):
        super().__init__(None, Qt.Window)
        self.cfg, self.home = cfg, cfg.home
        self.setWindowTitle("Suisheng · 模型管理")
        self.bridge = _Bridge()
        self.bridge.event.connect(self._on_event)
        self.bridge.finished.connect(self._on_finished)
        self.jobs = {}                   # key -> cancel Event
        self.auto = []                   # 首次打开时自动依次下载
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(12)
        self.head = QLabel(); self.head.setWordWrap(True)
        lay.addWidget(self.head)
        self.rows = {}
        for key, info in models.CATALOG.items():
            title = QLabel(f"<b>{info['title']}</b>"); title.setMinimumWidth(240)
            size = QLabel(f"{info['size_mb']/1000:.1f} GB" if info["size_mb"] >= 1000 else f"{info['size_mb']} MB")
            size.setMinimumWidth(60)
            bar = QProgressBar(); bar.setRange(0, 1000); bar.setTextVisible(False); bar.setFixedWidth(140)
            btn = QPushButton(); btn.setFixedWidth(80)
            btn.clicked.connect(lambda _=False, k=key: self._clicked(k))
            status = QLabel(); status.setStyleSheet("color: gray;")
            row = QHBoxLayout(); row.addWidget(title); row.addWidget(size); row.addWidget(bar); row.addWidget(btn)
            box = QVBoxLayout(); box.setSpacing(2); box.addLayout(row); box.addWidget(status)
            lay.addLayout(box)
            self.rows[key] = (bar, btn, status)
        self.llama_note = QLabel(); self.llama_note.setWordWrap(True); self.llama_note.setStyleSheet("color: gray;")
        lay.addWidget(self.llama_note)
        self.refresh()

    def installed(self, key):
        return models.installed(self.home, key)

    def refresh(self):
        for key, (bar, btn, status) in self.rows.items():
            busy, ok = key in self.jobs, self.installed(key)
            btn.setText("取消" if busy else ("已安装" if ok else "下载"))
            btn.setEnabled(busy or not ok)
            bar.setVisible(busy or not ok)
            if ok and not busy:
                status.setText("")
        has_llama = bool(find_server(self.cfg))
        self.llama_note.setText("" if has_llama else "⚠️ 没找到推理组件 llama.cpp（llama-server）：精修和翻译暂不可用。")

    def show_first_run(self):
        self.head.setText("欢迎使用 Suisheng！正在自动下载必需的「实时识别」模型（约 240MB，国内镜像，约 1 分钟）。\n"
                          "可选：Qwen 精修让粤语更准（建议 16GB 内存）；翻译把粤语 / 英文译成普通话。")
        self.auto = [k for k in ("sensevoice",) if not self.installed(k)]
        self._open()
        self._next_auto()

    def show_normal(self):
        self.head.setText(f"文件保存在：{self.home}\n默认从国内镜像（魔搭）下载，失败会自动换源；中断后再点下载会接着下。")
        self._open()

    def _open(self):
        self.refresh(); self.adjustSize(); self.show(); self.raise_(); self.activateWindow()

    def _next_auto(self):
        while self.auto:
            k = self.auto.pop(0)
            if not self.installed(k) and k not in self.jobs:
                self._start(k); return

    def _clicked(self, key):
        if key in self.jobs:
            self.jobs[key].set(); self.auto = []
        else:
            self._start(key)

    def _start(self, key):
        cancel = threading.Event()
        self.jobs[key] = cancel
        self.rows[key][2].setText("准备中…")

        def work():
            rc = models.download(self.home, key, emit=lambda **ev: self.bridge.event.emit(key, ev), cancel=cancel)
            self.bridge.finished.emit(key, rc)
        threading.Thread(target=work, daemon=True, name=f"download-{key}").start()
        self.refresh()

    def _on_event(self, key, ev):
        bar, _, status = self.rows[key]
        kind = ev.get("event")
        if kind == "progress":
            done, total = ev.get("done", 0), max(ev.get("total", 1), 1)
            bar.setValue(int(1000 * min(done / total, 1)))
            status.setText(f"{done/1e6:.0f} / {total/1e6:.0f} MB（{min(done/total, 1)*100:.0f}%）")
        elif kind == "source":
            status.setText(f"连接 {ev.get('endpoint')}…")
        elif kind == "reconnect":
            status.setText(f"网络卡住了，自动重连中（第 {ev.get('count', 1)} 次）…")
        elif kind == "retry":
            status.setText("当前下载源失败，换下一个…")
        elif kind == "error":
            status.setText(f"失败：{ev.get('error', '')}")

    def _on_finished(self, key, rc):
        self.jobs.pop(key, None)
        ok = self.installed(key)
        if ok:
            self.rows[key][2].setText("完成 ✓")
        self.refresh()
        self.changed.emit()
        if ok:
            self._next_auto()
        else:
            self.auto = []
