"""界面层唯一的平台差异：几处 Qt 管不到的窗口细节。其余界面代码全平台共用。"""
import sys


def hide_dock_icon():
    """macOS：作为菜单栏小工具运行，不在程序坞显示图标（打包版另在 Info.plist 设 LSUIElement）"""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().setActivationPolicy_(1)   # NSApplicationActivationPolicyAccessory
    except Exception:                                                # noqa: BLE001
        pass


def float_above_everything(widget):
    """macOS：让悬浮窗出现在所有桌面、也能盖在其他 App 的全屏视频上（Qt 没有这个接口）。
    Windows：Qt 的置顶 + 穿透标志已足够，无需额外处理。"""
    if sys.platform != "darwin":
        return
    try:
        import objc
        from AppKit import NSStatusWindowLevel
        win = objc.objc_object(c_void_p=int(widget.winId())).window()
        win.setLevel_(NSStatusWindowLevel)
        # canJoinAllSpaces(1<<0) | stationary(1<<4) | fullScreenAuxiliary(1<<8)
        win.setCollectionBehavior_((1 << 0) | (1 << 4) | (1 << 8))
        win.setHidesOnDeactivate_(False)
        win.setIgnoresMouseEvents_(True)
    except Exception as e:                                           # noqa: BLE001
        print("悬浮窗置顶设置失败：", e, file=sys.stderr)
