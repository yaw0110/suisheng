"""流式重采样到 16kHz 单声道（只依赖 numpy）：先低通（加窗 sinc FIR）防混叠，再按分数位置线性插值抽取。
对语音识别足够；保留跨块状态，块与块之间无缝。"""
import numpy as np

from .config import SR


class Resampler:
    def __init__(self, src_rate, dst_rate=SR, taps=63):
        self.src, self.dst = float(src_rate), float(dst_rate)
        self.step = self.src / self.dst                          # 每输出一个点前进多少个输入点
        self.pos = 0.0                                           # 下一个输出点在“已滤波缓冲”里的位置
        self.same = abs(self.src - self.dst) < 1e-6
        if not self.same:
            fc = 0.9 * (self.dst / 2) / self.src                 # 截止频率：目标奈奎斯特的 90%（归一化到输入采样率）
            n = np.arange(taps) - (taps - 1) / 2
            h = 2 * fc * np.sinc(2 * fc * n) * np.hamming(taps)
            self.h = (h / h.sum()).astype(np.float32)
            self.hist = np.zeros(taps - 1, np.float32)            # FIR 跨块状态
            self.buf = np.zeros(0, np.float32)                    # 已滤波、尚未取完的样本

    def __call__(self, x):
        x = np.asarray(x, np.float32)
        if self.same:
            return x
        y = np.convolve(np.concatenate([self.hist, x]), self.h, mode="valid").astype(np.float32)
        self.hist = np.concatenate([self.hist, x])[-(len(self.h) - 1):]
        self.buf = np.concatenate([self.buf, y])
        n_out = int(np.floor((len(self.buf) - 1 - self.pos) / self.step)) + 1 if len(self.buf) > self.pos + 1 else 0
        if n_out <= 0:
            return np.zeros(0, np.float32)
        idx = self.pos + np.arange(n_out) * self.step
        out = np.interp(idx, np.arange(len(self.buf)), self.buf).astype(np.float32)
        nxt = self.pos + n_out * self.step
        drop = int(np.floor(nxt))
        self.buf = self.buf[drop:]
        self.pos = nxt - drop
        return out


def to_mono_float(data, fmt_float, bits, channels):
    """原始 PCM 字节 → float32 单声道"""
    if fmt_float:
        a = np.frombuffer(data, np.float32 if bits == 32 else np.float64).astype(np.float32)
    elif bits == 16:
        a = np.frombuffer(data, "<i2").astype(np.float32) / 32768
    elif bits == 32:
        a = np.frombuffer(data, "<i4").astype(np.float32) / 2147483648
    else:
        raise ValueError(f"不支持的采样位数 {bits}")
    if channels > 1:
        a = a[: len(a) // channels * channels].reshape(-1, channels).mean(1)
    return a
