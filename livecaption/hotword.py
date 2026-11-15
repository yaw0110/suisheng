"""按发音（普通话拼音 / 粤语粤拼）把识别结果里的近音词纠正成热词表里的写法"""
import os, re
import pypinyin, ToJyutping, opencc

_s2hk = opencc.OpenCC("s2hk")
_PY_INIT = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "j", "q", "x", "r", "z", "c", "s", "y", "w"]
_JP_INIT = ["gw", "kw", "ng", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h", "z", "c", "s", "j", "w"]
# 口音/懒音里常混的声母视为相同
_SAME = {"zh": "z", "ch": "c", "sh": "s", "n": "l", "ng": "", "gw": "g", "kw": "k"}
_cache = {}

def _split(syl, inits):
    syl = re.sub(r"\d", "", syl or "")
    for i in inits:
        if syl.startswith(i): return _SAME.get(i, i), syl[len(i):]
    return "", syl

def _sounds(ch):
    if ch not in _cache:
        py = pypinyin.lazy_pinyin(ch)[0]
        jl = ToJyutping.get_jyutping_list(_s2hk.convert(ch))
        jp = jl[0][1] if jl and jl[0][1] else None
        _cache[ch] = (_split(py, _PY_INIT) if py != ch else None, _split(jp.split()[0], _JP_INIT) if jp else None)
    return _cache[ch]

def _syl_sim(a, b):
    if a is None or b is None: return 0.0
    if a == b: return 1.0
    s = 0.5 if a[0] == b[0] else 0.0
    if a[1] == b[1]: s += 0.5
    elif a[1] and b[1] and (a[1].startswith(b[1]) or b[1].startswith(a[1])): s += 0.3
    return s

def _score(cand, word):
    best = None
    for k in (0, 1):                     # 0=普通话拼音, 1=粤拼，取更像的那个
        sims = [_syl_sim(_sounds(c)[k], _sounds(w)[k]) for c, w in zip(cand, word)]
        if best is None or sum(sims) > sum(best): best = sims
    return best

class Hotwords:
    def __init__(self, path):
        self.path = path; self.mtime = None; self.words = []
    def _load(self):
        try: m = os.path.getmtime(self.path)
        except OSError: self.words = []; return
        if m == self.mtime: return
        self.mtime = m
        ws = [l.strip() for l in open(self.path, encoding="utf-8")]
        self.words = sorted({w for w in ws if w and not w.startswith("#") and len(w) >= 2}, key=len, reverse=True)
    def fix(self, text):
        self._load()
        if not self.words or not text: return text
        chars = list(text); n = len(chars); locked = [False] * n
        for w in self.words:                         # 1) 已经写对的热词先锁住，不再动
            for m in re.finditer(re.escape(w), text):
                for k in range(m.start(), m.end()): locked[k] = True
        cands = []                                   # 2) 收集所有近音候选，按相似度从高到低替换
        for w in self.words:
            L = len(w)
            for i in range(n - L + 1):
                cand = "".join(chars[i:i+L])
                if any(locked[i:i+L]) or not re.fullmatch(r"[一-鿿]+", cand): continue
                sims = _score(cand, w); tot = sum(sims)
                if L == 2: ok = tot >= 1.8
                else: ok = tot >= L - 0.6 or (sum(s < 1 for s in sims) == 1 and sims[0] == 1 and sims[-1] == 1)
                if ok: cands.append((tot / L, L, i, w))
        for _, L, i, w in sorted(cands, reverse=True):
            if any(locked[i:i+L]): continue
            chars[i:i+L] = list(w); locked[i:i+L] = [True] * L
        return "".join(chars)
