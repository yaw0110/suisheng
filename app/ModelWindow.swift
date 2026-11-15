// 首次设置 / 模型管理窗口：安装运行环境（仅安装版）、下载三个模型，带进度条。
import Cocoa

final class ModelWindow: NSObject, NSWindowDelegate {
    struct Row { let status: NSTextField; let bar: NSProgressIndicator; let button: NSButton }
    static let catalog: [(key: String, title: String, sizeMB: Int)] = [
        ("runtime", "运行环境（必需，只需安装一次）", 130),
        ("sensevoice", "实时识别（SenseVoice，必需）", 240),
        ("qwen_asr", "Qwen 精修（粤语更准，可选）", 2350),
        ("translator", "翻译（粤语/英文→普通话，可选）", 4100),
    ]
    let window: NSWindow
    var rows: [String: Row] = [:]
    var procs: [String: Process] = [:]
    var models: [String: ModelInfo] = [:]
    var autoQueue: [String] = []          // 首次打开时自动依次安装：运行环境 → 实时识别
    var onChange: (() -> Void)?
    var downloading: Bool { !procs.isEmpty }

    override init() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 320),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        super.init()
        window.title = "随声 · 模型管理"
        window.isReleasedWhenClosed = false
        window.delegate = self
    }

    func installed(_ k: String) -> Bool {
        k == "runtime" ? Env.runtimeReady : (models[k]?.installed ?? false)
    }

    func show(firstRun: Bool) {
        models = Models.status()
        let stack = NSStackView(); stack.orientation = .vertical; stack.alignment = .leading; stack.spacing = 14
        stack.edgeInsets = NSEdgeInsets(top: 18, left: 20, bottom: 18, right: 20)
        let head = NSTextField(wrappingLabelWithString: firstRun
            ? "欢迎使用随声！正在自动安装必需的「运行环境」和「实时识别」模型（共约 370MB，几分钟）。\n可选：Qwen 精修让粤语更准（建议 16GB 内存以上）；翻译把粤语/英文译成普通话（建议 24GB 内存）。"
            : "文件保存在：\(Env.home)\n默认从国内镜像下载，失败会自动换海外源；中断后再点下载会接着下。")
        head.preferredMaxLayoutWidth = 560
        stack.addArrangedSubview(head)
        rows = [:]
        for m in Self.catalog where m.key != "runtime" || Env.packaged {
            let title = NSTextField(labelWithString: m.title); title.font = .boldSystemFont(ofSize: 13)
            title.widthAnchor.constraint(equalToConstant: 250).isActive = true
            let size = NSTextField(labelWithString: m.sizeMB >= 1000 ? String(format: "%.1f GB", Double(m.sizeMB) / 1000) : "\(m.sizeMB) MB")
            size.textColor = .secondaryLabelColor; size.widthAnchor.constraint(equalToConstant: 60).isActive = true
            let bar = NSProgressIndicator(); bar.style = .bar; bar.isIndeterminate = false; bar.minValue = 0; bar.maxValue = 1
            bar.widthAnchor.constraint(equalToConstant: 120).isActive = true
            let status = NSTextField(labelWithString: ""); status.textColor = .secondaryLabelColor
            let btn = NSButton(title: "", target: self, action: #selector(buttonClicked(_:)))
            btn.identifier = NSUserInterfaceItemIdentifier(m.key)
            btn.widthAnchor.constraint(equalToConstant: 70).isActive = true
            let row = NSStackView(views: [title, size, bar, btn]); row.spacing = 10
            let col = NSStackView(views: [row, status]); col.orientation = .vertical; col.alignment = .leading; col.spacing = 2
            stack.addArrangedSubview(col)
            rows[m.key] = Row(status: status, bar: bar, button: btn)
        }
        window.contentView = stack
        window.setContentSize(stack.fittingSize)
        window.center()
        NSApp.activate(ignoringOtherApps: true)
        window.makeKeyAndOrderFront(nil)
        updateAll()
        if firstRun && !downloading {
            autoQueue = ["runtime", "sensevoice"].filter { !installed($0) && rows[$0] != nil }
            runNextAuto()
        }
    }

    func updateAll() { rows.keys.forEach { update($0) } }

    func update(_ k: String, text: String? = nil) {
        guard let r = rows[k] else { return }
        let busy = procs[k] != nil, ok = installed(k)
        let needsRuntime = k != "runtime" && !Env.runtimeReady
        r.button.title = busy ? "取消" : (ok ? "已安装" : (k == "runtime" ? "安装" : "下载"))
        r.button.isEnabled = busy || (!ok && !needsRuntime)
        r.bar.isHidden = ok && !busy
        if let t = text { r.status.stringValue = t }
        else if needsRuntime && !busy { r.status.stringValue = "需要先安装运行环境" }
        else if !busy { r.status.stringValue = ok ? "" : r.status.stringValue }
    }

    @objc func buttonClicked(_ b: NSButton) {
        guard let k = b.identifier?.rawValue else { return }
        if let p = procs[k] {
            autoQueue = []
            p.terminate(); procs[k] = nil; update(k, text: "已取消（再点会接着下）"); return
        }
        start(k)
    }

    func runNextAuto() {
        while let k = autoQueue.first {
            autoQueue.removeFirst()
            if !installed(k) { start(k); return }
        }
    }

    func start(_ k: String) {
        let p: Process
        if k == "runtime" {
            p = Process()
            p.executableURL = URL(fileURLWithPath: "/bin/bash")
            p.arguments = ["\(Env.res)/bootstrap.sh", Env.home, Env.res]
        } else {
            p = Env.python(["-m", "livecaption.models", "download", k, "--home", Env.home])
        }
        let pipe = Pipe(); p.standardOutput = pipe; p.standardError = FileHandle.nullDevice
        var buffer = Data()
        var lastError: String?
        pipe.fileHandleForReading.readabilityHandler = { [weak self] h in
            let d = h.availableData
            if d.isEmpty { h.readabilityHandler = nil; return }
            buffer.append(d)
            while let nl = buffer.firstIndex(of: 0x0A) {
                let line = buffer.subdata(in: buffer.startIndex..<nl); buffer.removeSubrange(buffer.startIndex...nl)
                guard let ev = try? JSONSerialization.jsonObject(with: line) as? [String: Any] else { continue }
                if ev["event"] as? String == "error" { lastError = ev["error"] as? String }
                DispatchQueue.main.async { self?.handle(k, ev) }
            }
        }
        p.terminationHandler = { [weak self] pr in
            DispatchQueue.main.async {
                guard let self = self, self.procs[k] === pr else { return }
                self.procs[k] = nil
                self.models = Models.status()
                let ok = self.installed(k)
                self.update(k, text: ok ? "完成 ✓" : "失败：\(lastError ?? "请检查网络后重试")")
                self.updateAll()
                self.onChange?()
                if ok { self.runNextAuto() } else { self.autoQueue = [] }
            }
        }
        do { try p.run(); procs[k] = p; update(k, text: "准备中…") }
        catch { update(k, text: "无法启动：\(error.localizedDescription)") }
    }

    func handle(_ k: String, _ ev: [String: Any]) {
        guard let r = rows[k] else { return }
        switch ev["event"] as? String {
        case "progress":
            let done = (ev["done"] as? Double) ?? 0, total = max((ev["total"] as? Double) ?? 1, 1)
            r.bar.doubleValue = min(done / total, 1)
            r.status.stringValue = String(format: "%.0f / %.0f MB（%.0f%%）", done / 1e6, total / 1e6, min(done / total, 1) * 100)
        case "stage":
            r.status.stringValue = ev["text"] as? String ?? ""
        case "source":
            r.status.stringValue = "连接 \((ev["endpoint"] as? String ?? "").replacingOccurrences(of: "https://", with: ""))…"
        case "retry":
            r.status.stringValue = "当前下载源失败，换下一个…"
        case "reconnect":
            r.status.stringValue = "网络卡住了，自动重连中（第 \(ev["count"] as? Int ?? 1) 次）…"
        default: break
        }
    }

    func windowWillClose(_ n: Notification) { onChange?() }
}
