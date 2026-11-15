"""测试 / 管道用的音频来源（系统声音见 sysaudio.py）：wav 文件或标准输入。都产出 0.1 秒一块的 float32 16k 单声道"""
import time

import numpy as np

from .config import SR

CHUNK = SR // 10


def file_source(path, stop, realtime=True):
    """realtime=True：按真实时钟喂入，处理慢了就会积压，和实时抓音一致；False：尽快喂入（可复现测试）"""
    import soundfile as sf
    a, sr = sf.read(path, dtype="float32")
    a = a if a.ndim == 1 else a.mean(1)
    if sr != SR:
        raise ValueError(f"{path} 需为 16kHz（实际 {sr}）")
    t0 = time.time()
    for i in range(0, len(a), CHUNK):
        if stop.is_set():
            return
        if realtime:
            time.sleep(max(0.0, t0 + (i + CHUNK) / SR - time.time()))
        yield a[i:i + CHUNK]
    for _ in range(15):                                         # 末尾补 1.5 秒静音，让最后一句定稿
        yield np.zeros(CHUNK, np.float32)
        if realtime:
            time.sleep(0.1)


def stdin_source(stop):
    """菜单栏 App 自己抓系统声音，通过管道把 16k/16bit/单声道 PCM 写到本进程的标准输入。App 关闭管道即结束"""
    import sys
    f = sys.stdin.buffer
    while not stop.is_set():
        b = f.read(CHUNK * 2)
        if not b:
            break
        if len(b) % 2:
            b = b[:-1]
        yield np.frombuffer(b, np.int16).astype(np.float32) / 32768
