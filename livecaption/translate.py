"""翻译：Hy-MT2-7B（MLX）把粤语口语 / 英文译成普通话书面中文"""
import re

YUE_MARK = re.compile(r"[哋咗嘅喺佢唔冇嚟係噉啲乜嘢睇俾嗰咩嘞喎噃吖啱攞揾嬲氹嗱咪啩]|而家|点解|边度|系咪|好似|仲有|琴日|听日|今朝")


def need_translate(text, lang=None):
    """粤语/英文才翻，普通话不翻。lang 来自 Qwen 的语种判断；没有时按文字特征猜"""
    if lang in ("Cantonese", "English"):
        return True
    letters = len(re.findall(r"[A-Za-z]", text))
    han = len(re.findall(r"[一-鿿]", text))
    return letters > han or bool(YUE_MARK.search(text))


class Translator:
    def __init__(self, model_dir, context=2):
        from mlx_lm import load
        from mlx_lm.sample_utils import make_sampler
        self.model, self.tok = load(str(model_dir))
        self.sampler = make_sampler(temp=0.0)
        self.context = context
        self.history = []
        self("hello")                                           # 预热

    def __call__(self, text):
        from mlx_lm import generate
        if self.history and self.context:
            prompt = ("\n".join(self.history[-self.context:]) +
                      "\n参考上面的信息，把下面的文本翻译成简体中文（普通话书面语），注意不需要翻译上文，也不要额外解释：\n" + text)
        else:
            prompt = "把下面的文本翻译成简体中文（普通话书面语），不要额外解释。\n\n" + text
        p = self.tok.apply_chat_template([{"role": "user", "content": prompt}],
                                         add_generation_prompt=True, tokenize=False)
        out = generate(self.model, self.tok, prompt=p, max_tokens=160, sampler=self.sampler).strip()
        self.history.append(text)
        return out.split("\n")[0].strip()
