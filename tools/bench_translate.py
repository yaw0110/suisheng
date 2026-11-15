"""对比“翻译”引擎：同样的句子、同样的提示词，不同的运行程序 / 模型。
用法：python -I tools/bench_translate.py <引擎> <句子.json> <输出.json>
引擎：mlx:<模型目录>   llama:<服务地址>
"""
import json
import resource
import sys
import time

from livecaption.textproc import TextProcessor

engine, src, out = sys.argv[1:4]
sents = json.load(open(src, encoding="utf-8"))
tp = TextProcessor("s", None)
kind, _, arg = engine.partition(":")
CONTEXT = 2


def build_prompt(text, history):
    if history:
        return ("\n".join(history[-CONTEXT:]) +
                "\n参考上面的信息，把下面的文本翻译成简体中文（普通话书面语），注意不需要翻译上文，也不要额外解释：\n" + text)
    return "把下面的文本翻译成简体中文（普通话书面语），不要额外解释。\n\n" + text


t0 = time.time()
if kind == "mlx":
    from mlx_lm import generate, load
    from mlx_lm.sample_utils import make_sampler
    model, tok = load(arg); sampler = make_sampler(temp=0.0)

    def run(prompt):
        p = tok.apply_chat_template([{"role": "user", "content": prompt}], add_generation_prompt=True, tokenize=False)
        return generate(model, tok, prompt=p, max_tokens=160, sampler=sampler)
else:
    import urllib.request

    def run(prompt):
        body = {"temperature": 0, "max_tokens": 160, "messages": [{"role": "user", "content": prompt}]}
        req = urllib.request.Request(arg + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=300))["choices"][0]["message"]["content"]
run(build_prompt("hello", []))
load = time.time() - t0

res, history, tot = [], [], 0.0
for s in sents:
    t = time.time(); o = run(build_prompt(s, history)); dt = time.time() - t
    history.append(s); tot += dt
    res.append({"src": s, "out": tp.tidy(o.strip().split("\n")[0]), "secs": round(dt, 2)})
summary = {"engine": engine, "load_secs": round(load, 1), "n": len(sents), "total_secs": round(tot, 1),
           "avg_per_sentence": round(tot / len(sents), 2), "max_secs": max(r["secs"] for r in res),
           "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1048576)}
json.dump({"summary": summary, "results": res}, open(out, "w"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False))
