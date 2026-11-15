"""悬浮字幕窗（PyObjC）：底部居中、置顶、鼠标穿透、全屏可见。必须在主线程运行。"""
import atexit
import queue

import objc
from AppKit import (NSApplication, NSApplicationActivationPolicyAccessory, NSBackingStoreBuffered, NSColor,
                    NSFont, NSMakeRect, NSPanel, NSScreen, NSStatusWindowLevel, NSTextAlignmentCenter,
                    NSTextField, NSWindowStyleMaskBorderless, NSWindowStyleMaskNonactivatingPanel)
from Foundation import NSObject, NSTimer

from .bus import END, FINAL, PARTIAL, REVISE, TRANS

LINE_BREAK_TRUNCATE_HEAD = 4      # 一行放不下时截掉开头，保留最新的字


def _quit(app):
    """Cocoa 的 terminate 直接调用 C exit()，不会执行 Python 的 atexit（清理就绪标记、关掉 audiotee），这里先手动执行"""
    atexit._run_exitfuncs()
    app.terminate_(None)


def _label(panel, W, y, h, size, alpha):
    l = NSTextField.alloc().initWithFrame_(NSMakeRect(12, y, W - 24, h))
    for f in ("setBezeled_", "setDrawsBackground_", "setEditable_", "setSelectable_"):
        getattr(l, f)(False)
    l.setTextColor_(NSColor.colorWithCalibratedWhite_alpha_(1, alpha))
    l.setFont_(NSFont.boldSystemFontOfSize_(size))
    l.setAlignment_(NSTextAlignmentCenter)
    l.cell().setLineBreakMode_(LINE_BREAK_TRUNCATE_HEAD)
    panel.contentView().addSubview_(l)
    return l


class _Ticker(NSObject):
    """每 50ms 从消息队列取事件更新界面"""
    @objc.python_method
    def setup(self, app, bus, stop, top, mid, bot):
        self.app, self.bus, self.stop = app, bus, stop
        self.top, self.mid, self.bot = top, mid, bot
        self.top_id = -1
        return self

    def tick_(self, _t):
        while True:
            try:
                k, v = self.bus.q.get_nowait()
            except queue.Empty:
                break
            if k == END:
                _quit(self.app); return
            elif k == FINAL:
                self.top_id, s = v
                self.top.setStringValue_(s); self.bot.setStringValue_("")
                if self.mid:
                    self.mid.setStringValue_("")
            elif k == REVISE:                                   # Qwen 精修结果：还是屏幕上那句就替换
                sid, s = v
                if sid == self.top_id:
                    self.top.setStringValue_(s)
            elif k == TRANS and self.mid:                       # 译文（晚到一句也照样显示）
                sid, s = v
                if sid >= self.top_id - 1:
                    self.mid.setStringValue_(s)
            elif k == PARTIAL:
                self.bot.setStringValue_(v)
        if self.stop.is_set():                                  # Ctrl-C / SIGTERM / 父进程退出
            _quit(self.app)


def run_overlay(bus, display, show_translation, stop, on_ready=None):
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    font = display.font
    sf = NSScreen.mainScreen().visibleFrame()
    W = min(display.width, sf.size.width * 0.8)
    H = font * (5.0 if show_translation else 3.6)
    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(sf.origin.x + (sf.size.width - W) / 2, sf.origin.y + display.bottom_margin, W, H),
        NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel, NSBackingStoreBuffered, False)
    panel.setLevel_(NSStatusWindowLevel)
    panel.setOpaque_(False); panel.setHasShadow_(False)
    panel.setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0, display.opacity))
    panel.setIgnoresMouseEvents_(True)
    panel.setCollectionBehavior_((1 << 0) | (1 << 8))           # 所有桌面 + 全屏辅助
    if show_translation:
        top = _label(panel, W, H * 0.70, H * 0.27, font * 0.75, 0.6)   # 上一句原文（较暗）
        mid = _label(panel, W, H * 0.38, H * 0.32, font * 0.9, 1.0)    # 上一句译文（黄色）
        mid.setTextColor_(NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.86, 0.35, 1.0))
        bot = _label(panel, W, H * 0.04, H * 0.32, font, 1.0)          # 当前句（实时）
    else:
        top = _label(panel, W, H * 0.52, H * 0.42, font * 0.8, 0.6)
        bot = _label(panel, W, H * 0.06, H * 0.46, font, 1.0)
        mid = None
    bot.setStringValue_("字幕已启动，等待声音…")
    panel.orderFrontRegardless()
    if on_ready:
        on_ready()
    ticker = _Ticker.alloc().init().setup(app, bus, stop, top, mid, bot)
    NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(0.05, ticker, "tick:", None, True)
    app.run()
