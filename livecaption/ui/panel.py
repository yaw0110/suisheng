"""主控制面板：开始 / 停止 + 常用设置。托盘图标可能被挤掉（Mac 刘海 / Windows 托盘折叠区），面板是稳定的入口。"""
import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)

MODES = [("speech", "说话（剧集 / 视频）"), ("song", "歌曲")]
LANGS = [("auto", "自动识别"), ("yue", "粤语"), ("zh", "普通话"), ("en", "英文")]
SCRIPTS = [("s", "简体"), ("hk", "繁体（香港）"), ("tw", "繁体（台湾）")]


class Panel(QWidget):
    toggle = Signal()
    setting = Signal(str, object)          # 设置项改变
    action = Signal(str)                   # models / hotwords / config / logs / quit

    def __init__(self, settings, version):
        super().__init__(None, Qt.Window)
        self.setWindowTitle("Suisheng")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 18, 22, 18)
        lay.setSpacing(14)

        self.btn = QPushButton()
        f = QFont(); f.setPixelSize(18); f.setBold(True); self.btn.setFont(f)
        self.btn.setMinimumHeight(48)
        self.btn.clicked.connect(self.toggle)
        lay.addWidget(self.btn)
        self.status = QLabel(); self.status.setAlignment(Qt.AlignCenter); self.status.setStyleSheet("color: gray;")
        lay.addWidget(self.status)

        form = QFormLayout(); form.setLabelAlignment(Qt.AlignRight)
        self.combos = {}
        for key, title, opts in (("mode", "模式", MODES), ("lang", "识别语言", LANGS), ("script", "字幕文字", SCRIPTS)):
            cb = QComboBox()
            for val, text in opts:
                cb.addItem(text, val)
            cb.setCurrentIndex(max(0, cb.findData(settings[key])))
            cb.currentIndexChanged.connect(lambda _i, k=key, c=cb: self.setting.emit(k, c.currentData()))
            form.addRow(title, cb)
            self.combos[key] = cb
        lay.addLayout(form)

        self.checks = {}
        for key, title in (("refine", "Qwen 精修（粤语更准）"), ("translate", "翻译成普通话")):
            c = QCheckBox(title); c.setChecked(bool(settings[key]))
            c.toggled.connect(lambda on, k=key: self.setting.emit(k, on))
            lay.addWidget(c)
            self.checks[key] = c
        self.hint = QLabel(); self.hint.setWordWrap(True); self.hint.setStyleSheet("color: gray;")
        lay.addWidget(self.hint)

        row = QHBoxLayout()
        for key, text in (("models", "模型管理"), ("hotwords", "热词"), ("config", "配置"), ("logs", "字幕记录")):
            b = QPushButton(text); b.clicked.connect(lambda _=False, k=key: self.action.emit(k)); row.addWidget(b)
        lay.addLayout(row)
        foot = QHBoxLayout()
        ver = QLabel(f"Suisheng {version}"); ver.setStyleSheet("color: gray;")
        quit_btn = QPushButton("退出 Suisheng"); quit_btn.clicked.connect(lambda: self.action.emit("quit"))
        foot.addWidget(ver); foot.addStretch(1); foot.addWidget(quit_btn)
        lay.addLayout(foot)
        tip = QLabel("关掉这个窗口字幕照常运行。要再打开它：再次打开「Suisheng」，或点菜单栏 / 托盘的羽毛笔"
                     + ("；字幕运行时程序坞图标会暂时隐藏（这样字幕才能盖住全屏视频）。" if sys.platform == "darwin" else "。"))
        tip.setWordWrap(True); tip.setStyleSheet("color: gray; font-size: 11px;")
        lay.addWidget(tip)

    def set_state(self, state):
        self.btn.setText({"off": "▶  开始字幕", "starting": "启动中…", "on": "■  停止字幕", "stopping": "关闭中…"}[state])
        self.btn.setEnabled(state in ("off", "on"))
        self.status.setText({"off": "字幕已关闭", "starting": "正在加载模型…", "on": "字幕运行中（改设置会自动重启字幕）",
                             "stopping": ""}[state])

    def set_available(self, refine_ok, translate_ok):
        self.checks["refine"].setEnabled(refine_ok)
        self.checks["translate"].setEnabled(translate_ok)
        miss = [n for n, ok in (("精修", refine_ok), ("翻译", translate_ok)) if not ok]
        self.hint.setText(f"{'、'.join(miss)}模型未下载：点「模型管理」下载后可用。" if miss else "")

    def bring_up(self):
        self.show(); self.raise_(); self.activateWindow()
