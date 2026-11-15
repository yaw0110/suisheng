"""随声 · 主程序（托盘 / 菜单栏图标 + 悬浮字幕 + 模型管理），macOS / Windows 同一份代码。

左键点托盘图标：开始 / 停止字幕；右键（Mac 也可按住 Control 点）：设置菜单。
字幕引擎（识别、精修、翻译）在本进程的后台线程里运行。"""
import json
import os
import queue
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QCursor, QDesktopServices, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .. import models
from ..bus import END, FINAL, PARTIAL, REVISE, TRANS
from ..config import DEFAULT_HOTWORDS
from ..engine import Engine, make_config
from ..llama import find_server
from ..runtime import Runtime
from .models_window import ModelsWindow
from .overlay import Overlay
from .platform import hide_dock_icon

ASSETS = Path(__file__).resolve().parent.parent / "assets"
DEFAULTS = {"mode": "speech", "lang": "auto", "script": "s", "refine": True, "translate": False}
CONFIG_TEMPLATE = """# 随声 · 自定义配置：只写要修改的项，其余沿用默认值。改完重新开启字幕生效。
# 全部可调项及说明见程序内置的 default_config.toml，例如：
# [display]
# font = 32            # 字号
# bottom_margin = 120  # 离屏幕底部的距离
#
# [segment.speech]
# pause_none = 0.7     # 停顿多久断句（秒），越小出字越快但越容易切碎
"""


class Settings:
    """用户设置（模式、语言、精修、翻译），存在数据目录的 settings.json"""
    def __init__(self, home):
        self.path = Path(home) / "settings.json"
        try:
            self.v = {**DEFAULTS, **json.loads(self.path.read_text(encoding="utf-8"))}
        except (OSError, ValueError):
            self.v = dict(DEFAULTS)

    def __getitem__(self, k):
        return self.v[k]

    def set(self, k, val):
        self.v[k] = val
        self.path.write_text(json.dumps(self.v, ensure_ascii=False, indent=1), encoding="utf-8")


class App(QObject):
    started = Signal(object)             # 后台线程启动完成（engine 或 异常）

    def __init__(self, cfg):
        super().__init__()
        self.base_cfg, self.home = cfg, cfg.home
        self._prepare_home()
        self.settings = Settings(self.home)
        self.engine = None
        self.state = "off"               # off / starting / on / stopping
        self.top_id = -1
        self.overlay = Overlay(cfg.display)
        self.models_win = ModelsWindow(cfg)
        self.models_win.changed.connect(self._refresh_icon)
        self.started.connect(self._on_started)

        icon = QIcon()
        if sys.platform == "darwin":
            icon.addFile(str(ASSETS / "trayTemplate.png")); icon.addFile(str(ASSETS / "trayTemplate@2x.png"))
            icon.setIsMask(True)                                  # 菜单栏按深浅色自动反色
        else:
            icon.addFile(str(ASSETS / "icon.png"))
        self.tray = QSystemTrayIcon(icon)
        self.tray.activated.connect(self._on_tray)
        self.menu = QMenu()
        self.menu.aboutToShow.connect(self._build_menu)
        if sys.platform != "darwin":
            self.tray.setContextMenu(self.menu)                  # Windows：右键弹菜单，左键单独处理
        self.tray.show()
        self._refresh_icon()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._poll)
        self.timer.start(50)
        if not models.installed(self.home, "sensevoice"):
            self.models_win.show_first_run()
        elif os.environ.get("LIVECAPTION_AUTOSTART"):            # 测试用：启动后自动开始字幕
            QTimer.singleShot(300, self.start)

    # ---------- 准备 ----------
    def _prepare_home(self):
        for d in ("", "models", "logs", "runtime"):
            (self.home / d).mkdir(parents=True, exist_ok=True)
        hw = self.home / "hotwords.txt"
        if not hw.exists():
            hw.write_text(DEFAULT_HOTWORDS.read_text(encoding="utf-8"), encoding="utf-8")
        cf = self.home / "config.toml"
        if not cf.exists():
            cf.write_text(CONFIG_TEMPLATE, encoding="utf-8")

    # ---------- 托盘 ----------
    def _on_tray(self, reason):
        R = QSystemTrayIcon.ActivationReason
        right = (QGuiApplication.mouseButtons() & QtRight()) or (QGuiApplication.keyboardModifiers() & QtCtrl())
        if reason == R.Context or (reason == R.Trigger and sys.platform == "darwin" and right):
            if sys.platform == "darwin":
                self.menu.popup(QCursor.pos())
        elif reason == R.Trigger:
            self.toggle()

    def _refresh_icon(self):
        tip = {"off": "随声：已关闭（点击开始，右键设置）", "starting": "随声：启动中…",
               "on": "随声：字幕运行中（点击停止，右键设置）", "stopping": "随声：关闭中…"}[self.state]
        self.tray.setToolTip(tip)

    def _build_menu(self):
        m, s = self.menu, self.settings
        m.clear()
        act = m.addAction("■ 停止字幕" if self.state == "on" else "▶ 开始字幕", self.toggle)
        act.setEnabled(self.state in ("on", "off"))
        m.addSeparator()

        def radio(title, key, options):
            sub = m.addMenu(title)
            grp = QActionGroup(sub)
            for val, text in options:
                a = QAction(text, sub, checkable=True, checked=(s[key] == val))
                a.triggered.connect(lambda _=False, v=val: self._set(key, v))
                grp.addAction(a); sub.addAction(a)
        radio("模式", "mode", [("speech", "说话（剧集 / 视频）"), ("song", "歌曲")])
        radio("识别语言", "lang", [("auto", "自动"), ("yue", "粤语"), ("zh", "普通话"), ("en", "英文")])
        radio("字幕文字", "script", [("s", "简体"), ("hk", "繁体（香港）"), ("tw", "繁体（台湾）")])
        m.addSeparator()
        llama = bool(find_server(self.base_cfg))
        for key, model, title in (("refine", "qwen_asr", "Qwen 精修（粤语更准）"), ("translate", "translator", "翻译成普通话")):
            if llama and models.installed(self.home, model):
                a = QAction(title, m, checkable=True, checked=bool(s[key]))
                a.triggered.connect(lambda on, k=key: self._set(k, on))
                m.addAction(a)
            else:
                m.addAction(f"{title}（未下载，点此下载…）", self.models_win.show_normal)
        m.addSeparator()
        m.addAction("模型管理…", self.models_win.show_normal)
        m.addAction("编辑热词表…", lambda: self._open(self.home / "hotwords.txt"))
        m.addAction("编辑配置（字号、断句等）…", lambda: self._open(self.home / "config.toml"))
        m.addAction("查看字幕记录", lambda: self._open(self.home / "logs" / "latest.txt", self.home / "logs"))
        m.addSeparator()
        from .. import __version__
        about = m.addAction(f"随声 {__version__}"); about.setEnabled(False)
        m.addAction("退出", self.quit)

    def _open(self, path, fallback=None):
        p = path if Path(path).exists() or fallback is None else fallback
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))

    def _set(self, key, val):
        self.settings.set(key, val)
        if self.state == "on":                                   # 运行中改设置：自动重启字幕
            self.stop(then_start=True)

    # ---------- 开 / 关 ----------
    def toggle(self):
        if self.state == "off":
            self.start()
        elif self.state == "on":
            self.stop()

    def start(self):
        if not models.installed(self.home, "sensevoice"):
            self.models_win.show_first_run(); return
        s = self.settings
        cfg = make_config(home=str(self.home), mode=s["mode"], lang=s["lang"], script=s["script"],
                          no_qwen=not s["refine"], translate=bool(s["translate"]))
        self.state = "starting"; self._refresh_icon()
        self.overlay.set_translation_visible(bool(s["translate"]))
        self.overlay.clear(); self.overlay.set_text("bot", "字幕启动中…"); self.overlay.show()

        def work():
            try:
                self.started.emit(Engine(cfg, ui=True).start())
            except Exception as e:                               # noqa: BLE001
                self.started.emit(e)
        threading.Thread(target=work, daemon=True, name="engine-start").start()

    def _on_started(self, result):
        if isinstance(result, Exception):
            self.state = "off"; self.overlay.hide(); self._refresh_icon()
            QMessageBox.warning(None, "随声", f"字幕启动失败：{result}\n\n如果是 macOS，请到「系统设置 → 隐私与安全性 → "
                                              "屏幕与系统录音」允许本程序录制系统声音。")
            return
        self.engine, self.state, self.top_id = result, "on", -1
        self.overlay.set_text("bot", "字幕已启动，等待声音…")
        self._refresh_icon()

    def stop(self, then_start=False):
        eng, self.engine = self.engine, None
        self.state = "stopping"; self._refresh_icon()

        def work():
            if eng:
                eng.stop()
            QTimer.singleShot(0, self, lambda: self._stopped(then_start))
        threading.Thread(target=work, daemon=True, name="engine-stop").start()

    def _stopped(self, then_start):
        self.state = "off"; self.overlay.hide(); self._refresh_icon()
        if then_start:
            self.start()

    def quit(self):
        if self.engine:
            self.engine.stop()
        QApplication.quit()

    # ---------- 字幕事件 ----------
    def _poll(self):
        eng = self.engine
        if not eng or not eng.bus:
            return
        o = self.overlay
        while True:
            try:
                k, v = eng.bus.q.get_nowait()
            except queue.Empty:
                break
            if k == FINAL:
                self.top_id, s = v
                o.set_text("top", s); o.set_text("bot", ""); o.set_text("mid", "")
            elif k == REVISE:
                sid, s = v
                if sid == self.top_id:
                    o.set_text("top", s)
            elif k == TRANS:
                sid, s = v
                if sid >= self.top_id - 1:
                    o.set_text("mid", s)
            elif k == PARTIAL:
                o.set_text("bot", v)
            elif k == END and self.state == "on":                # 音频源意外结束
                self.stop()


def QtRight():
    from PySide6.QtCore import Qt
    return Qt.RightButton


def QtCtrl():
    from PySide6.QtCore import Qt
    return Qt.ControlModifier


def run_app(cfg):
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("随声")
    app.setWindowIcon(QIcon(str(ASSETS / "icon.png")))
    hide_dock_icon()
    rt = Runtime(cfg.paths.runtime)
    if not rt.acquire_lock():
        QMessageBox.information(None, "随声", "随声已经在运行了（看看菜单栏 / 托盘里的羽毛笔图标）。")
        return 3
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(None, "随声", "当前系统没有可用的托盘区域。")
        return 1
    main_app = App(cfg)                                          # noqa: F841  保持引用
    return app.exec()


def main():
    from .. import config
    sys.exit(run_app(config.load([])))


if __name__ == "__main__":
    main()
