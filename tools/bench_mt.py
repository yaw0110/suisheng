import sys, time
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler
B = sys.argv[1]
YUE = ["我哋八字都未有一撇，就顶心顶肺啦！", "几时先可以好似人哋咁白头到老啊？", "哇！你睇佢个样啊，笑到见牙唔见眼。",
       "系啊，兰姐啊，今日咧好多人报名。", "我今朝开咗个 meeting，老板话个 project 要下个礼拜 deliver，真系好赶。",
       "你哋今日食咗饭未呀？我哋听日去旺角行街，顺便睇场戏好唔好？", "嗱，我帮佢学车搞掂啦。"]
EN = ["Exactly English that you would use in everyday life that you hear in movies and TV shows.",
      "So why don't you tell us a little bit about this lesson for today?",
      "Today we are going to talk about how large language models are changing software development."]
PROMPTS = {
  "Hy-MT2-7B-4bit": lambda t: "把下面的文本翻译成简体中文（普通话书面语），不要额外解释。\n\n" + t,
  "Qwen3-4B-Instruct-2507-4bit": lambda t: ("你是字幕翻译器。把下面一句字幕翻译成自然的简体中文普通话书面语"
       "（粤语口语要改写成普通话，英文要译成中文），只输出译文。\n\n" + t),
}
samp = make_sampler(temp=0.0)
for name, mk in PROMPTS.items():
    t = time.time(); model, tok = load(f"{B}/models/{name}"); print(f"\n===== {name}（加载 {time.time()-t:.1f}s）=====")
    def tr(text):
        msgs = [{"role": "user", "content": mk(text)}]
        p = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
        return generate(model, tok, prompt=p, max_tokens=120, sampler=samp).strip()
    tr("你好")
    for s in YUE + EN:
        t = time.time(); o = tr(s); print(f"[{time.time()-t:.2f}s] {s}\n        → {o}")
    del model
