// 随声 · 菜单栏 App
// 左键：开始 / 停止字幕；右键（或按住 Control 点）：设置菜单。
// 识别和显示都在 Python 字幕进程（python -m livecaption）里，这里只负责开关、设置和模型下载。
import Cocoa

// MARK: - 运行环境：安装版 / 开发版自动判断
// 安装版：App 包里只有本程序一个可执行文件；Python 运行环境首次打开时由 bootstrap.sh 下载安装到用户目录
//（程序自己下载的文件不带“隔离”标记，不会被 macOS 拦截）。开发版：用源码目录的 .venv。
enum Env {
    static let res = Bundle.main.resourcePath ?? ""
    static let packaged = FileManager.default.fileExists(atPath: "\(res)/runtime.lock")
    static let devBase = NSString(string: UserDefaults.standard.string(forKey: "basePath")
                                  ?? "~/github/live-caption-test").expandingTildeInPath
    /// 用户数据目录：运行环境、模型、热词、配置、字幕记录
    static let home = packaged
        ? NSString(string: "~/Library/Application Support/LiveCaption").expandingTildeInPath : devBase
    static let python = packaged ? "\(home)/pyenv/python/bin/python3" : "\(devBase)/.venv/bin/python"
    static var readyFile: String { "\(home)/runtime/ready" }
    /// 本版本 App 需要的运行环境编号（打包时写进 runtime.lock）
    static let runtimeID: String = {
        guard let s = try? String(contentsOfFile: "\(res)/runtime.lock", encoding: .utf8) else { return "" }
        for line in s.split(separator: "\n") where line.hasPrefix("RUNTIME_ID=") {
            return line.dropFirst("RUNTIME_ID=".count).trimmingCharacters(in: CharacterSet(charactersIn: "\"' "))
        }
        return ""
    }()
    static var runtimeReady: Bool {
        guard packaged else { return FileManager.default.isExecutableFile(atPath: python) }
        let id = (try? String(contentsOfFile: "\(home)/pyenv/.runtime-id", encoding: .utf8))?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return id == runtimeID && FileManager.default.isExecutableFile(atPath: python)
    }
    static var version: String { Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "dev" }

    static func prepareHome() {
        let fm = FileManager.default
        for d in ["", "/models", "/logs"] {
            try? fm.createDirectory(atPath: home + d, withIntermediateDirectories: true)
        }
        guard packaged else { return }
        if !fm.fileExists(atPath: "\(home)/hotwords.txt") {
            try? fm.copyItem(atPath: "\(res)/hotwords.txt", toPath: "\(home)/hotwords.txt")
        }
        if !fm.fileExists(atPath: "\(home)/config.toml") {
            let tpl = """
            # 随声 · 自定义配置：只写要修改的项，其余沿用默认值。改完重新开启字幕生效。
            # 全部可调项及说明见：\(res)/config.default.toml
            # 例：
            # [display]
            # font = 32            # 字号
            # bottom_margin = 120  # 离屏幕底部的距离
            #
            # [segment.speech]
            # pause_none = 0.7     # 停顿多久断句（秒），越小出字越快但越容易切碎

            """
            try? tpl.write(toFile: "\(home)/config.toml", atomically: true, encoding: .utf8)
        }
    }

    static func python(_ args: [String]) -> Process {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: python)
        p.arguments = ["-I", "-B"] + args                  // -B：不在 App 包里写 .pyc（会破坏签名）
        p.currentDirectoryURL = URL(fileURLWithPath: home)
        return p
    }
}

// MARK: - 模型状态
struct ModelInfo { let key: String; let title: String; let sizeMB: Int; var installed: Bool }

enum Models {
    static let order = ["sensevoice", "qwen_asr", "translator"]
    static func status() -> [String: ModelInfo] {
        guard Env.runtimeReady else { return [:] }
        let p = Env.python(["-m", "livecaption.models", "status", "--home", Env.home])
        let pipe = Pipe(); p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        guard (try? p.run()) != nil else { return [:] }
        let data = pipe.fileHandleForReading.readDataToEndOfFile(); p.waitUntilExit()
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: [String: Any]] else { return [:] }
        var out: [String: ModelInfo] = [:]
        for (k, v) in obj {
            out[k] = ModelInfo(key: k, title: v["title"] as? String ?? k, sizeMB: v["size_mb"] as? Int ?? 0,
                               installed: v["installed"] as? Bool ?? false)
        }
        return out
    }
}

// MARK: - 菜单栏
final class AppDelegate: NSObject, NSApplicationDelegate {
    var item: NSStatusItem!
    var proc: Process?
    var readyTimer: Timer?
    let capture = SystemAudioCapture()
    var audioPipe: Pipe?
    var busy = ""                                   // "启动中…" / "关闭中…"：期间忽略左键
    var models: [String: ModelInfo] = [:]
    let modelWindow = ModelWindow()
    let prefs = UserDefaults.standard
    var mode: String { prefs.string(forKey: "mode") ?? "speech" }
    var lang: String { prefs.string(forKey: "lang") ?? "auto" }
    var useQwen: Bool { prefs.object(forKey: "qwen") as? Bool ?? true }
    var translate: Bool { prefs.object(forKey: "translate") as? Bool ?? false }
    var running: Bool { proc?.isRunning ?? false }
    func has(_ k: String) -> Bool { models[k]?.installed ?? false }

    func applicationDidFinishLaunching(_ n: Notification) {
        Env.prepareHome()
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let b = item.button {
            b.target = self; b.action = #selector(clicked); b.sendAction(on: [.leftMouseUp, .rightMouseUp])
        }
        signal(SIGPIPE, SIG_IGN)                                 // Python 退出后再写管道不至于让 App 崩溃
        modelWindow.onChange = { [weak self] in self?.models = Models.status(); self?.refresh() }
        models = Models.status()
        refresh()
        if !Env.runtimeReady || !has("sensevoice") { modelWindow.show(firstRun: true) }
    }

    // MARK: 点击与菜单
    @objc func clicked() {
        let e = NSApp.currentEvent
        if e?.type == .rightMouseUp || e?.modifierFlags.contains(.control) == true {
            models = Models.status()
            item.menu = buildMenu(); item.button?.performClick(nil); item.menu = nil
        } else if busy.isEmpty {
            toggle()
        }
    }

    func buildMenu() -> NSMenu {
        let m = NSMenu()
        func add(_ title: String, _ sel: Selector, on: Bool? = nil, value: String? = nil) {
            let i = NSMenuItem(title: title, action: sel, keyEquivalent: "")
            i.target = self; i.representedObject = value
            if let on = on { i.state = on ? .on : .off }
            m.addItem(i)
        }
        add(running ? "■ 停止字幕" : "▶ 开始字幕", #selector(toggle))
        m.addItem(.separator())
        for (k, t) in [("speech", "说话模式（剧集 / 视频）"), ("song", "歌曲模式")] {
            add(t, #selector(setMode(_:)), on: mode == k, value: k)
        }
        m.addItem(.separator())
        for (k, t) in [("auto", "自动识别语言"), ("yue", "粤语"), ("zh", "普通话"), ("en", "英文")] {
            add(t, #selector(setLang(_:)), on: lang == k, value: k)
        }
        m.addItem(.separator())
        if has("qwen_asr") { add("Qwen 精修（更准，多占约 2.5GB 内存）", #selector(toggleQwen), on: useQwen) }
        else { add("Qwen 精修（未下载，点此下载…）", #selector(showModels)) }
        if has("translator") { add("翻译成中文（粤语/英文→普通话，多占约 4GB）", #selector(toggleTranslate), on: translate) }
        else { add("翻译成中文（未下载，点此下载…）", #selector(showModels)) }
        m.addItem(.separator())
        add("模型管理…", #selector(showModels))
        add("编辑热词表…", #selector(openHotwords))
        add("编辑配置（断句、字号等）…", #selector(openConfig))
        add("查看字幕记录", #selector(openLog))
        m.addItem(.separator())
        let about = NSMenuItem(title: "随声 \(Env.version)\(Env.packaged ? "" : "（开发版）")", action: nil, keyEquivalent: "")
        about.isEnabled = false; m.addItem(about)
        let q = NSMenuItem(title: "退出", action: #selector(quit), keyEquivalent: "q"); q.target = self; m.addItem(q)
        return m
    }

    func refresh() {
        let img = NSImage(systemSymbolName: running ? "captions.bubble.fill" : "captions.bubble",
                          accessibilityDescription: "随声")
        img?.isTemplate = true
        item.button?.image = img
        item.button?.imagePosition = .imageLeading
        item.button?.title = busy.isEmpty ? "" : " " + busy
        item.button?.toolTip = running ? "字幕运行中（点击关闭，右键设置）" : "字幕已关闭（点击开启，右键设置）"
    }

    func alert(_ title: String, _ text: String) {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert(); a.messageText = title; a.informativeText = text; a.runModal()
    }

    // MARK: 启动 / 停止
    @objc func toggle() { running ? stop() : start() }

    func start() {
        models = Models.status()
        guard Env.runtimeReady && has("sensevoice") else { modelWindow.show(firstRun: true); return }
        let fm = FileManager.default
        try? fm.removeItem(atPath: Env.readyFile)
        let logPath = "\(Env.home)/logs/app.log"
        if !fm.fileExists(atPath: logPath) { fm.createFile(atPath: logPath, contents: nil) }
        let log = FileHandle(forWritingAtPath: logPath); log?.seekToEndOfFile()

        var args = ["-m", "livecaption", "--home", Env.home, "--mode", mode, "--lang", lang,
                    "--parent-pid", String(ProcessInfo.processInfo.processIdentifier), "--audio-stdin"]
        if !useQwen || !has("qwen_asr") { args.append("--no-qwen") }
        if translate && has("translator") { args.append("--translate") }
        let p = Env.python(args)
        let audio = Pipe()                                    // App 抓的系统声音 → Python 标准输入
        audioPipe = audio
        p.standardInput = audio
        p.standardOutput = FileHandle.nullDevice              // 字幕记录由 Python 写到 logs/
        p.standardError = log
        p.terminationHandler = { [weak self] pr in
            DispatchQueue.main.async {
                guard let self = self else { return }
                self.stopCapture()
                let wasStarting = self.busy == "启动中…"
                self.readyTimer?.invalidate(); self.busy = ""; self.refresh()
                if pr.terminationStatus == 3 {
                    self.alert("已有字幕在运行", "同一时间只能开一个字幕。")
                } else if wasStarting {
                    self.alert("字幕启动失败", "详情见 \(logPath)")
                }
            }
        }
        do { try p.run(); proc = p } catch { alert("启动失败", "\(error)"); return }
        busy = "启动中…"; refresh()
        let t0 = Date()
        readyTimer?.invalidate()
        readyTimer = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] t in
            guard let self = self else { t.invalidate(); return }
            if fm.fileExists(atPath: Env.readyFile) {                // 字幕窗出来了，再开始抓声音
                t.invalidate(); self.busy = ""; self.refresh()
                do { try self.capture.start(writingTo: audio.fileHandleForWriting.fileDescriptor) }
                catch {
                    self.alert("无法获取系统声音", "请到「系统设置 → 隐私与安全性 → 屏幕与系统录音」允许「随声」，然后重新开启。\n（\(error.localizedDescription)）")
                    self.stop()
                }
            } else if Date().timeIntervalSince(t0) > 90 {
                t.invalidate(); self.busy = ""; self.refresh(); self.stop()
                self.alert("字幕启动超时", "详情见 \(logPath)")
            }
        }
    }

    func stopCapture() {
        capture.stop()
        try? audioPipe?.fileHandleForWriting.close()            // Python 读到结尾就会退出
        audioPipe = nil
    }

    func stop() {
        guard let p = proc, p.isRunning else { refresh(); return }
        readyTimer?.invalidate(); busy = "关闭中…"; refresh()
        stopCapture()
        p.terminationHandler = { [weak self] _ in DispatchQueue.main.async { self?.busy = ""; self?.refresh() } }
        p.interrupt()                                         // SIGINT：让字幕进程正常收尾
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { if p.isRunning { p.terminate() } }
    }

    func restartIfRunning() {
        guard running else { return }
        stop()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3.5) { self.start() }
    }

    // MARK: 设置
    @objc func setMode(_ s: NSMenuItem) { prefs.set(s.representedObject, forKey: "mode"); restartIfRunning() }
    @objc func setLang(_ s: NSMenuItem) { prefs.set(s.representedObject, forKey: "lang"); restartIfRunning() }
    @objc func toggleQwen() { prefs.set(!useQwen, forKey: "qwen"); restartIfRunning() }
    @objc func toggleTranslate() { prefs.set(!translate, forKey: "translate"); restartIfRunning() }
    @objc func showModels() { modelWindow.show(firstRun: false) }
    @objc func openHotwords() { NSWorkspace.shared.open(URL(fileURLWithPath: "\(Env.home)/hotwords.txt")) }
    @objc func openConfig() {
        let path = "\(Env.home)/config.toml"
        // 用文本编辑打开（.toml 默认可能没有关联程序）
        NSWorkspace.shared.open([URL(fileURLWithPath: path)], withApplicationAt: URL(fileURLWithPath: "/System/Applications/TextEdit.app"),
                                configuration: NSWorkspace.OpenConfiguration())
    }
    @objc func openLog() {
        let latest = "\(Env.home)/logs/latest.txt"
        NSWorkspace.shared.open(URL(fileURLWithPath: FileManager.default.fileExists(atPath: latest) ? latest : "\(Env.home)/logs"))
    }
    @objc func quit() {
        if modelWindow.downloading {
            NSApp.activate(ignoringOtherApps: true)
            let a = NSAlert(); a.messageText = "模型还在下载"; a.informativeText = "退出会中断下载（下次可接着下）。确定退出吗？"
            a.addButton(withTitle: "退出"); a.addButton(withTitle: "取消")
            if a.runModal() != .alertFirstButtonReturn { return }
            modelWindow.procs.values.forEach { $0.terminate() }
        }
        stop()
        DispatchQueue.main.asyncAfter(deadline: .now() + (running ? 3.2 : 0)) { NSApp.terminate(nil) }
    }
    func applicationWillTerminate(_ n: Notification) {
        capture.stop()
        if let p = proc, p.isRunning { p.terminate() }
        modelWindow.procs.values.forEach { $0.terminate() }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
