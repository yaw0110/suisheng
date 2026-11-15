// 抓系统声音（Core Audio Tap，代码来自 vendor/audiotee 的 AudioTeeCore，编译进本 App）
// 输出 16kHz / 16bit / 单声道 PCM，写进管道交给 Python 字幕进程（python -m livecaption --audio-stdin）。
// 由 App 自己抓音：系统录音权限算在「随声」名下，App 包里也不需要额外的可执行文件。
import CoreAudio
import Foundation

/// 把音频写进管道。写端设为非阻塞：Python 一时处理不过来就丢掉这一小块，绝不卡住 Core Audio 的音频线程。
final class PipeAudioOutput: AudioOutputHandler {
    let fd: Int32
    init(fd: Int32) {
        self.fd = fd
        _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK)
    }
    func handleAudioData(_ pointer: UnsafeRawPointer, count: Int) {
        var written = 0
        while written < count {
            let r = write(fd, pointer.advanced(by: written), count - written)
            if r > 0 { written += r }
            else if r < 0 && errno == EINTR { continue }
            else { break }                       // EAGAIN（管道满）/ EPIPE（Python 已退出）：丢弃
        }
    }
    func handleMetadata(_ metadata: AudioStreamMetadata) {}
    func handleStreamStart() {}
    func handleStreamStop() {}
}

final class SystemAudioCapture {
    private var tap: AudioTapManager?
    private var recorder: AudioRecorder?
    var isRunning: Bool { recorder != nil }

    func start(writingTo fd: Int32) throws {
        stop()
        let cfg = TapConfiguration(processes: [], muteBehavior: .unmuted, isExclusive: true, isMono: true)
        let m = AudioTapManager()
        try m.setupAudioTap(with: cfg)
        guard let dev = m.getDeviceID() else { throw NSError(domain: "LiveCaption", code: 1,
                                                             userInfo: [NSLocalizedDescriptionKey: "无法创建系统声音采集设备"]) }
        let r = try AudioRecorder(deviceID: dev, outputHandler: PipeAudioOutput(fd: fd),
                                  convertToSampleRate: 16000, chunkDuration: 0.1)
        try r.startRecording()
        tap = m; recorder = r
    }

    func stop() {
        recorder?.stopRecording()
        recorder = nil
        tap = nil                                    // AudioTapManager 释放时会销毁 tap 和聚合设备
    }
}
