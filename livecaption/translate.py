"""翻译：Hy-MT2（GGUF，经 llama.cpp）把粤语口语 / 英文译成普通话书面中文"""
import re

YUE_MARK = re.compile(r"[哋咗嘅喺佢唔冇嚟係噉啲乜嘢睇俾嗰咩嘞喎噃吖啱攞揾嬲氹嗱咪啩]|而家|点解|边度|系咪|好似|仲有|琴日|听日|今朝")


def need_translate(text, lang=None):
    """粤语/英文才翻，普通话不翻。lang 来自 Qwen 的语种判断；没有时按文字特征猜"""
    if lang in ("Cantonese", "English"):
        return True
    letters = len(re.findall(r"[A-Za-z]", text))
    han = len(re.findall(r"[一-鿿]", text))
    return letters > han or bool(YUE_MARK.search(text))


def build_prompt(text, history, context=2):
    if history and context:
        return ("\n".join(history[-context:]) +
                "\n参考上面的信息，把下面的文本翻译成简体中文（普通话书面语），注意不需要翻译上文，也不要额外解释：\n" + text)
    return "把下面的文本翻译成简体中文（普通话书面语），不要额外解释。\n\n" + text


class Translator:
    def __init__(self, server, context=2):
        self.server, self.context = server, context
        self.history = []
        self.server.chat(build_prompt("hello", []), max_tokens=16)   # 预热

    def __call__(self, text):
        out = self.server.chat(build_prompt(text, self.history, self.context), max_tokens=160)
        self.history.append(text)
        del self.history[:-8]
        return out.strip().split("\n")[0].strip()
