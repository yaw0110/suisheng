"""配置：默认配置（包内 default_config.toml）← 用户配置（<home>/config.toml，只需写要改的项）← 命令行参数

home（用户数据目录：模型、热词、配置、字幕记录）：
  - 从源码目录运行：项目根目录
  - App 安装版：~/Library/Application Support/LiveCaption（由 App 用 --home 传入）
"""
import argparse
import os
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

PKG = Path(__file__).resolve().parent
SR = 16000  # 全流程统一 16kHz 单声道
DEFAULT_CONFIG = PKG / "default_config.toml"
DEFAULT_HOTWORDS = PKG / "default_hotwords.txt"
if sys.platform == "darwin":
    APP_HOME = Path.home() / "Library/Application Support/LiveCaption"
elif sys.platform == "win32":
    APP_HOME = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "LiveCaption"
else:
    APP_HOME = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "livecaption"


def default_home():
    """从源码目录运行用项目根目录；安装版（PyInstaller 打包）用用户数据目录；环境变量 LIVECAPTION_HOME 可覆盖"""
    if os.environ.get("LIVECAPTION_HOME"):
        return Path(os.environ["LIVECAPTION_HOME"]).expanduser()
    src_root = PKG.parent
    if not getattr(sys, "frozen", False) and (src_root / "pyproject.toml").exists():
        return src_root
    return APP_HOME


def parse_args(argv=None):
    ap = argparse.ArgumentParser(prog="livecaption", description="Mac 本地实时字幕")
    ap.add_argument("--mode", default="speech", choices=["speech", "song"], help="speech=说话(剧集/视频)  song=唱歌")
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "yue", "en"], help="识别语言")
    ap.add_argument("--script", default="s", choices=["s", "hk", "tw"], help="s=简体(默认) hk=港繁 tw=台繁")
    ap.add_argument("--no-qwen", action="store_true", help="不用 Qwen3-ASR 精修定稿，只用 SenseVoice")
    ap.add_argument("--translate", action="store_true", help="把英文/粤语定稿句翻译成普通话中文（Hy-MT2-7B）")
    ap.add_argument("--font", type=float, help="字号（默认见配置）")
    ap.add_argument("--pause", type=float, help="无标点时的断句停顿阈值(秒)")
    ap.add_argument("--max-sent", type=float, help="单句最长秒数")
    ap.add_argument("--refresh", type=float, help="SenseVoice 滚动重识别的最小间隔(秒)")
    ap.add_argument("--home", help="用户数据目录（模型/热词/配置/记录），默认见模块说明")
    ap.add_argument("--audiotee", help="audiotee 可执行文件路径（命令行运行时用）")
    ap.add_argument("--audio-stdin", action="store_true",
                    help="从标准输入读 16k/16bit/单声道 PCM（菜单栏 App 自己抓声音后通过管道传入）")
    ap.add_argument("--hotwords", help="热词表路径（默认 <home>/hotwords.txt）")
    ap.add_argument("--config", help="配置文件（默认 <home>/config.toml，不存在则用内置默认）")
    ap.add_argument("--file", help="测试用：用 16k wav 代替系统音频（按真实时钟喂入）")
    ap.add_argument("--fast", action="store_true",
                    help="测试用（配合 --file）：不按真实时钟，按音频时间推进，结果可复现，用于回归测试")
    ap.add_argument("--no-ui", action="store_true", help="不显示悬浮窗，只打印")
    ap.add_argument("--debug", action="store_true", help="打印每条字幕的音频位置和耗时")
    ap.add_argument("--record", help="把抓到的系统音频另存为 16k wav（复现问题用）")
    ap.add_argument("--parent-pid", type=int, help="父进程（菜单栏 App）PID：父进程退出时字幕跟着退出")
    return ap.parse_args(argv)


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_raw(home, config_path=None):
    with open(DEFAULT_CONFIG, "rb") as f:
        raw = tomllib.load(f)
    user = Path(config_path) if config_path else Path(home) / "config.toml"
    if user.exists():
        with open(user, "rb") as f:
            raw = _merge(raw, tomllib.load(f))
    return raw


def load(argv=None):
    args = parse_args(argv)
    home = Path(args.home).expanduser() if args.home else default_home()
    raw = load_raw(home, args.config)
    m, seg = raw["models"], raw["segment"]
    mdir = home / m["dir"]
    mode = seg[args.mode]
    hot = Path(args.hotwords) if args.hotwords else home / "hotwords.txt"
    return SimpleNamespace(
        args=args,
        home=home,
        paths=SimpleNamespace(
            sensevoice=mdir / m["sensevoice"],
            qwen_asr=mdir / m["qwen_asr"],
            translator=mdir / m["translator"],
            audiotee=Path(args.audiotee) if args.audiotee else home / m["audiotee"],
            hotwords=hot if hot.exists() else DEFAULT_HOTWORDS,
            logs=home / "logs",
            runtime=home / "runtime",
        ),
        asr=SimpleNamespace(threads=raw["asr"]["threads"],
                            refresh=args.refresh or raw["asr"]["refresh"]),
        seg=SimpleNamespace(
            pause_end=mode["pause_end"],
            pause_comma=mode["pause_comma"],
            pause_none=args.pause or mode["pause_none"],
            min_tokens=seg["min_tokens"],
            max_sentence=args.max_sent or seg["max_sentence"],
            long_pause=seg["long_pause"],
        ),
        filt=SimpleNamespace(**raw["filter"]),
        llama=SimpleNamespace(**raw.get("llama", {"server": "", "gpu_layers": 99, "threads": 0})),
        refine=SimpleNamespace(**raw["refine"]),
        translate=SimpleNamespace(**raw["translate"]),
        display=SimpleNamespace(**{**raw["display"], **({"font": args.font} if args.font else {})}),
    )
