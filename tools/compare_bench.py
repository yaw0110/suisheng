"""汇总对比 data/bench 里的结果。用法：python -I tools/compare_bench.py refine|mt <基线.json> <其他.json>..."""
import difflib
import json
import re
import sys
from pathlib import Path

mode, base, *others = sys.argv[1:]
norm = lambda t: re.sub(r"[\W_]", "", t).lower()


def cer(ref, hyp):
    r, h = norm(ref), norm(hyp)
    d = list(range(len(h) + 1))
    for i, a in enumerate(r, 1):
        p, d[0] = d[0], i
        for j, b in enumerate(h, 1):
            p, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, p + (a != b))
    return d[-1], len(r)


B = json.load(open(base))
print(f"基线：{B['summary']}")
if mode == "refine":
    truth = {}
    for f in Path("data/samples").glob("*.txt"):
        truth[f"samples/{f.stem}"] = f.read_text(encoding="utf-8").strip()
    for name in others:
        O = json.load(open(name)); print(f"\n===== {O['summary']}")
        e = n = 0; same = 0; diffs = []
        for k, b in B["results"].items():
            o = O["results"].get(k)
            if o is None: continue
            if norm(b["text"]) == norm(o["text"]): same += 1
            else: diffs.append((k, b["text"], o["text"]))
            if k in truth:
                a, c = cer(truth[k], o["text"]); e += a; n += c
        tb = "".join(norm(v["text"]) for v in B["results"].values()); to = "".join(norm(O["results"][k]["text"]) for k in B["results"] if k in O["results"])
        print(f"与基线逐句完全相同（忽略标点）：{same}/{len(B['results'])}；整体文字相似度 {difflib.SequenceMatcher(None, tb, to).ratio():.3f}")
        if n: print(f"有标准答案的 4 段样音字错率：{e}/{n} = {e/n:.1%}")
        for k, b, o in diffs: print(f"  [{k}]\n      基线：{b}\n      本次：{o}")
else:
    for name in others:
        O = json.load(open(name)); print(f"\n===== {O['summary']}")
        same = sum(norm(b["out"]) == norm(o["out"]) for b, o in zip(B["results"], O["results"]))
        print(f"译文与基线完全相同（忽略标点）：{same}/{len(B['results'])}")
        for b, o in zip(B["results"], O["results"]):
            mark = "  " if norm(b["out"]) == norm(o["out"]) else "≠ "
            print(f"{mark}原文：{b['src']}\n      基线（{b['secs']}s）：{b['out']}\n      本次（{o['secs']}s）：{o['out']}")
