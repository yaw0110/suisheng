"""断句：根据 SenseVoice 逐字时间戳里的字间停顿，决定在哪里切句、音频从哪里切开。

纯函数，不依赖模型，可单独测试（见 tests/test_segmenter.py）。
"""
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np


class Token(NamedTuple):
    text: str     # 字 / 英文词片段（已并入后面的标点）
    ts: float     # 起始时间，秒，相对当前缓冲区开头
    punct: int    # 字后标点：0=无 1=逗号类 2=句末


@dataclass
class SegParams:
    pause_end: float = 0.3     # 句末标点后，停顿多久就断
    pause_comma: float = 0.55  # 逗号后
    pause_none: float = 0.9    # 无标点
    min_tokens: int = 4        # 少于这么多字/词的碎片不单独成句（除非停顿很长）
    max_sentence: float = 10.0 # 缓冲超过这么长还没断，就强制找地方切
    long_pause: float = 1.6    # “很长的停顿”：碎片也允许单独成句


def find_splits(toks, buflen, p: SegParams):
    """自然停顿处的断句点：返回 [(在第 i 个字之后断开, 音频切点秒)]"""
    n = len(toks)
    if n == 0:
        return []
    diffs = [toks[i + 1].ts - toks[i].ts for i in range(n - 1)]
    med = float(np.median(diffs)) if diffs else 0.25           # 当前语速（唱歌时字被拉长，阈值随之变大）
    pts, start = [], 0
    for i in range(n):
        nxt = toks[i + 1].ts if i + 1 < n else buflen
        gap = nxt - toks[i].ts                                  # 本字起点到下一字起点（含本字发音时长）
        base = (p.pause_none, p.pause_comma, p.pause_end)[toks[i].punct]
        thr = max(base, 2.2 * med) + 0.15                       # +0.15 ≈ 一个字本身的发音时长
        if i == n - 1:
            thr += 0.2                                          # 句尾：多等一点，确认真的停了
        short = (i - start + 1) < p.min_tokens
        if gap >= thr and (not short or gap >= p.long_pause or (i == n - 1 and gap >= thr + 0.5)):
            if i + 1 < n:                                       # 切在两字间隙中间偏后，别吃掉下一字的起音
                cut = min(nxt - 0.2, (toks[i].ts + 0.25 + nxt) / 2)
            else:
                cut = min(toks[i].ts + 0.6, buflen - 0.05)
            pts.append((i, max(cut, toks[i].ts + 0.1)))
            start = i + 1
    return pts


def forced_split(toks, p: SegParams):
    """句子太长又没有自然停顿：优先句号处，其次逗号，最后最大字间隔"""
    cand = range(p.min_tokens - 1, len(toks) - 2) or range(len(toks) - 2)
    i = max(cand, key=lambda k: (toks[k].punct, toks[k + 1].ts - toks[k].ts))
    return [(i, min(toks[i + 1].ts - 0.2, (toks[i].ts + 0.25 + toks[i + 1].ts) / 2))]


def plan_splits(toks, buflen, p: SegParams):
    pts = find_splits(toks, buflen, p)
    if not pts and buflen > p.max_sentence and len(toks) > 2:
        pts = forced_split(toks, p)
    return pts
