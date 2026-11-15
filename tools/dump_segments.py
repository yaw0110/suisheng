"""把一段录音按当前的实时断句切成一句一句的 wav（可复现模式），供不同精修引擎用完全相同的输入做对比。
用法：python -I tools/dump_segments.py data/samples/drama75.wav data/segments/drama75
"""
import json
import sys
import threading
from pathlib import Path

import soundfile as sf

from livecaption import config
from livecaption.audio import file_source
from livecaption.bus import Bus
from livecaption.captioner import Captioner
from livecaption.sensevoice import SenseVoice
from livecaption.textproc import TextProcessor

wav, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)


class Dump:                      # 顶替精修线程：只把每句的音频存下来
    use_qwen, use_mt, enabled = True, False, True

    def __init__(self):
        self.items = []

    def submit(self, sid, audio, text):
        sf.write(out / f"{sid:03d}.wav", audio, 16000)
        self.items.append({"sid": sid, "secs": round(len(audio) / 16000, 2), "sensevoice": text})


cfg = config.load(["--file", wav, "--fast", "--no-ui"])
stop = threading.Event()
dump = Dump()
Captioner(cfg, Bus(ui=False), TextProcessor("s", cfg.paths.hotwords),
          SenseVoice(cfg.paths.sensevoice, "auto", cfg.asr.threads, cfg.filt.token_rel_energy),
          dump, file_source(wav, stop, realtime=False), stop).run()
(out / "segments.json").write_text(json.dumps(dump.items, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{len(dump.items)} 句 → {out}")
