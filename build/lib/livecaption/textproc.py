"""文本后处理：统一简繁、去掉幻听字符、中英文间加空格、热词纠正"""
import re

import opencc

from .hotword import Hotwords

JUNK = re.compile(r"[぀-ヿ가-힯ᄀ-ᇿ]")   # 只要中英粤：去掉幻听出来的假名/韩文
LEAD_PUNCT = re.compile(r"^[，。、？！；：,.?!;:…\s]+")


def meaningful(t):
    """是否值得显示：至少 2 个字/字母，且不是单个英文词（多半是噪声幻听）"""
    if len(re.sub(r"[\s\W_]", "", t)) < 2:
        return False
    if re.fullmatch(r"[A-Za-z' ]+[.,!?]*", t) and len(t.split()) <= 1:
        return False
    return True


class TextProcessor:
    def __init__(self, script="s", hotwords_path=None):
        self.t2s = opencc.OpenCC("t2s")                          # Qwen 输出简繁混杂，先统一成简体
        self.conv = None if script == "s" else opencc.OpenCC({"hk": "s2hk", "tw": "s2twp"}[script])
        self.hot = Hotwords(hotwords_path) if hotwords_path else None

    def tidy(self, t):
        t = re.sub(r"\s+", " ", JUNK.sub("", self.t2s.convert(t))).strip()
        t = t.replace("～", "").replace("~", "")
        t = LEAD_PUNCT.sub("", t)
        t = re.sub(r"([A-Za-z])([一-鿿])", r"\1 \2", re.sub(r"([一-鿿])([A-Za-z])", r"\1 \2", t))
        if self.hot:
            t = self.hot.fix(t)
        if self.conv and t:
            t = re.sub(r"繫(?![統列數鞋上於])", "係", self.conv.convert(t))   # 粤语「係」被 s2hk 误转为「繫」
        return t
