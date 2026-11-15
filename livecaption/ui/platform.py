"""界面层唯一的平台差异：几处 Qt 管不到的窗口细节（只在 macOS 上需要）。其余界面代码全平台共用。"""
import sys

MAC = sys.platform == "darwin"


def set_overlay_mode(on):
    """macOS 规定：只有“菜单栏小工具”（无程序坞图标）的 App，窗口才能显示在别的 App 的全屏画面上。
    所以字幕开着时切成小工具模式（程序坞图标暂时隐藏），关掉字幕再切回普通模式。Windows 不需要。"""
    if not MAC:
        return
    try:
        from AppKit import NSApplication
        app = NSApplication.sharedApplication()
        app.setActivationPolicy_(1 if on else 0)      # 1=Accessory 小工具  0=Regular 普通（有程序坞图标）
    except Exception as e:                            # noqa: BLE001
        print("切换应用模式失败：", e, file=sys.stderr)


def float_above_everything(widget):
    """macOS：悬浮窗出现在所有桌面、能盖住全屏视频、不抢焦点、鼠标穿透（Qt 没有这些接口）。
    Windows：Qt 的置顶 + 穿透标志已足够。"""
    if not MAC:
        return
    try:
        import objc
        from AppKit import NSStatusWindowLevel
        win = objc.objc_object(c_void_p=int(widget.winId())).window()
        win.setStyleMask_(win.styleMask() | (1 << 7))  # NSWindowStyleMaskNonactivatingPanel：不激活本 App
        win.setLevel_(NSStatusWindowLevel)
        # canJoinAllSpaces(1<<0) | stationary(1<<4) | fullScreenAuxiliary(1<<8)
        win.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 8))
        win.setHidesOnDeactivate_(False)
        win.setIgnoresMouseEvents_(True)
        win.orderFrontRegardless()
    except Exception as e:                            # noqa: BLE001
        print("悬浮窗置顶设置失败：", e, file=sys.stderr)
