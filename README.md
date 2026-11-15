<p align="center"><img src="app/icon/icon_1024.png" width="128" alt="随声"></p>

# 随声

**本地实时字幕（macOS / Windows）**：抓取电脑正在播放的声音（视频、剧集、直播、播客、歌曲），实时生成**英文 / 普通话 / 粤语**字幕，可选把粤语、英文**翻译成普通话**。识别和翻译全部在本机完成，声音和文字不会上传。

*Echo — on-device live captions (English / Mandarin / Cantonese) with optional translation to Mandarin. One Python codebase for macOS and Windows.*

- 控制面板 + 菜单栏 / 托盘图标；屏幕底部悬浮字幕（置顶、可拖动、悬停显示 × 关闭）
- 按说话停顿断句；粤语口语字（咗、哋、喺、嘅）照样写得出；说话 / 歌曲两种模式
- 每句定稿后用更准的模型精修；人名热词按拼音 / 粤拼近音纠正
- 输出简体（可选港繁 / 台繁），字幕记录按天保存

## 安装

从 [Releases](https://github.com/yaw0110/suisheng/releases) 下载对应系统的安装包。

**macOS**（Apple 芯片，macOS 14.2+）：打开 `Suisheng-<版本>-macos-arm64.dmg`，把「随声」拖进「应用程序」。首次打开若提示“无法验证开发者”，到「系统设置 → 隐私与安全性」点“仍要打开”（免费签名，只需一次）。第一次开始字幕时允许“录制系统声音”。详见 [安装说明](packaging/安装说明.txt)。

**Windows**（10 / 11，x64）：安装程序制作中。

首次打开会自动下载「实时识别」模型（约 240MB，默认国内魔搭镜像）；Qwen 精修（2.5GB）、翻译（1.1GB）可在「模型管理」里按需下载。

## 工作原理

```
随声（一个进程，Python）
├─ ui/          PySide6：控制面板 · 托盘 · 悬浮字幕 · 模型管理（全平台一套代码）
├─ sysaudio.py  抓系统声音 → 16k 单声道（macOS：Core Audio Tap / catap；Windows：WASAPI 回环 / PyAudioWPatch）
├─ captioner.py [识别线程] SenseVoice（sherpa-onnx）每 ~0.3 秒对未定稿音频重识别 → 按字间停顿断句
├─ refiner.py   [精修线程] 每句定稿：Qwen3-ASR 重新识别 → Hy-MT2 翻译（都经 llama.cpp 的 llama-server）
├─ textproc.py  简繁统一、热词纠正；bus.py 线程间消息 + 字幕记录
└─ models.py    模型下载：魔搭优先 → hf-mirror → huggingface.co；断点续传、卡死重连、sha256 校验
```

平台相关的代码只有两处：`livecaption/sysaudio.py`（抓系统声音）和 `livecaption/ui/platform.py`（macOS 上让悬浮字幕盖住全屏视频）。

| 环节 | 模型 | 运行方式 | 每句耗时（M3） |
|---|---|---|---|
| 实时识别 | SenseVoice-Small int8 | sherpa-onnx（ONNX Runtime） | 0.1–0.25 s / 次 |
| 精修（可选） | Qwen3-ASR-1.7B Q8_0 | llama.cpp（Mac Metal / Win CUDA·Vulkan·CPU） | 0.44 s（只用 CPU 1.2 s） |
| 翻译（可选） | Hy-MT2-1.8B Q4_K_M（高配可换 7B） | llama.cpp | 0.30 s（只用 CPU 1.1 s） |

引擎选型的对比数据见 [PR #1](https://github.com/yaw0110/suisheng/pull/1)。

## 从源码运行 / 开发

```bash
git clone https://github.com/yaw0110/suisheng.git && cd suisheng
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/pip install --no-deps -e .
.venv/bin/python -I -m livecaption.models download sensevoice   # 下载模型到 ./models（另有 qwen_asr / translator）
brew install llama.cpp                                         # 精修 / 翻译需要 llama-server（打包版已内置）
.venv/bin/python -I -m livecaption.app                          # 打开图形界面
```

```bash
.venv/bin/python -I -m livecaption --file 录音.wav --no-ui --debug   # 命令行：用录音复现问题
.venv/bin/python -I tests/test_segmenter.py                           # 断句单元测试
.venv/bin/python -I tests/regression.py                               # 端到端回归（需自备 data/samples/*.wav）
packaging/build_mac.sh                                                # 打包 macOS DMG（约 1 分钟，含自检）
```

| 路径 | 内容 |
|---|---|
| `livecaption/` | Python 包；`default_config.toml` 默认配置（用户在数据目录的 `config.toml` 里只写要改的项）；`model_manifest.json` 模型清单与校验和 |
| `livecaption/ui/` | 界面：`app.py` 主程序、`panel.py` 控制面板、`overlay.py` 悬浮字幕、`models_window.py` 模型管理 |
| `packaging/` | `suisheng.spec`（PyInstaller，全平台共用）、`build_mac.sh`、`entry.py`、安装说明 |
| `app/icon/` | 图标源文件（`make_icon.swift` 生成） |
| `tests/` `tools/` | 测试；引擎对比 / 测速脚本 |

用户数据目录：macOS `~/Library/Application Support/LiveCaption`，Windows `%LOCALAPPDATA%\LiveCaption`（模型、热词、配置、字幕记录）。

## 第三方组件与模型

本仓库不包含模型文件，模型在使用时由用户从公开源下载，请遵守各自的许可：

| 组件 | 来源 | 许可 |
|---|---|---|
| SenseVoice-Small（sherpa-onnx 导出版） | [FunAudioLLM/SenseVoice](https://github.com/FunAudioLLM/SenseVoice) · [k2-fsa/sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) | 模型遵循 FunASR 模型许可 |
| Qwen3-ASR-1.7B（GGUF） | [QwenLM/Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR) · ggml-org | Apache-2.0 |
| Hy-MT2（GGUF） | [Tencent-Hunyuan](https://huggingface.co/tencent/Hy-MT2-7B) | 腾讯混元模型许可 |
| llama.cpp（随安装包分发 llama-server） | [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT |
| PySide6 / Qt | [Qt for Python](https://doc.qt.io/qtforpython-6/) | LGPL-3.0 |
| catap · PyAudioWPatch | [sbetko/catap](https://github.com/sbetko/catap) · [s0d3s/PyAudioWPatch](https://github.com/s0d3s/PyAudioWPatch) | MIT |

## 许可

本项目代码以 [MIT](LICENSE) 许可发布；模型与第三方组件遵循各自许可（见上表）。
