"""抓系统声音（唯一与平台相关的模块）。统一接口：
    system_audio(stop) -> 迭代器，产出 0.1 秒一块的 16kHz 单声道 float32
macOS：Core Audio Tap（catap 库，Python 进程内调用，需要“录制系统声音”权限）
Windows：WASAPI 回环采集（PyAudioWPatch）
"""
import queue
import sys
import time

import numpy as np

from .config import SR
from .resample import Resampler, to_mono_float

CHUNK = SR // 10


def _rechunk(blocks, stop, silence_after=0.3):
    """把不定长的块整理成 0.1 秒一块；源头长时间没数据（没声音时 Windows 回环会停发）就补静音，保证时钟不停"""
    buf = np.zeros(0, np.float32)
    last = time.time()
    while not stop.is_set():
        try:
            b = blocks.get(timeout=0.1)
        except queue.Empty:
            b = None
        if b is None:
            if time.time() - last >= silence_after:
                b = np.zeros(CHUNK, np.float32)
            else:
                continue
        last = time.time()
        buf = np.concatenate([buf, b])
        while len(buf) >= CHUNK:
            yield buf[:CHUNK]
            buf = buf[CHUNK:]


def _mac(stop):
    import catap
    blocks = queue.Queue(maxsize=600)
    state = {}

    def on_buffer(b):
        f = b.format
        if "rs" not in state:
            state["rs"] = Resampler(f.sample_rate)
        x = state["rs"](to_mono_float(b.data, f.is_float, f.bits_per_sample, f.num_channels))
        try:
            blocks.put_nowait(x)
        except queue.Full:
            pass                                                 # 下游跟不上：丢掉最旧的数据比卡住音频线程好

    session = catap.record_system_audio(mono=True, on_buffer=on_buffer)
    session.start()
    try:
        yield from _rechunk(blocks, stop)
    finally:
        try:
            session.close()
        except Exception:                                        # noqa: BLE001
            pass


def _win(stop):
    import pyaudiowpatch as pyaudio
    blocks = queue.Queue(maxsize=600)
    p = pyaudio.PyAudio()
    try:
        info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        spk = p.get_device_info_by_index(info["defaultOutputDevice"])
        if not spk.get("isLoopbackDevice"):
            for lb in p.get_loopback_device_info_generator():
                if spk["name"] in lb["name"]:
                    spk = lb
                    break
        rate, ch = int(spk["defaultSampleRate"]), int(spk["maxInputChannels"])
        rs = Resampler(rate)

        def cb(data, frames, t, status):
            x = rs(to_mono_float(data, False, 16, ch))
            try:
                blocks.put_nowait(x)
            except queue.Full:
                pass
            return (None, pyaudio.paContinue)

        st = p.open(format=pyaudio.paInt16, channels=ch, rate=rate, input=True,
                    input_device_index=spk["index"], frames_per_buffer=rate // 20, stream_callback=cb)
        st.start_stream()
        try:
            yield from _rechunk(blocks, stop)
        finally:
            st.stop_stream(); st.close()
    finally:
        p.terminate()


def system_audio(stop):
    if sys.platform == "darwin":
        return _mac(stop)
    if sys.platform == "win32":
        return _win(stop)
    raise RuntimeError(f"暂不支持的平台：{sys.platform}")
