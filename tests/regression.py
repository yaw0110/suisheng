"""回归测试：用 --fast 可复现模式把固定测试音频跑一遍完整流程（SenseVoice + 断句 + Qwen 精修 + 翻译），
和 tests/golden/ 里的基准逐字比较。可复现模式下同样的代码每次输出完全相同，有差异就说明行为变了。

运行：.venv/bin/python -I tests/regression.py            （约 1 分钟）
确认新输出是改进后更新基准：.venv/bin/python -I tests/regression.py --update
"""
import sys as _sys
for _s in (_sys.stdout, _sys.stderr):
    _s.reconfigure(encoding="utf-8", errors="replace")
import difflib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ["concat_test", "drama75"]
THRESHOLD = 0.999   # 可复现模式：应当完全一致


def run_case(name):
    out = subprocess.run([sys.executable, "-I", "-m", "livecaption", "--file", str(ROOT / "data/samples" / f"{name}.wav"),
                          "--fast", "--no-ui", "--translate"], cwd=ROOT, capture_output=True, text=True).stdout
    return "\n".join(re.sub(r"^\d\d:\d\d:\d\d ", "", l) for l in out.splitlines() if l.strip())


def main():
    update = "--update" in sys.argv
    ok = True
    for name in CASES:
        got = run_case(name)
        gold = ROOT / "tests/golden" / f"{name}.txt"
        if update:
            gold.write_text(got + "\n", encoding="utf-8"); print("已更新", gold); continue
        want = gold.read_text(encoding="utf-8").strip()
        ratio = difflib.SequenceMatcher(None, want, got).ratio()
        status = "通过" if ratio >= THRESHOLD else "失败"
        ok &= ratio >= THRESHOLD
        print(f"[{status}] {name}: 相似度 {ratio:.2f}（{len(got.splitlines())} 行 / 基准 {len(want.splitlines())} 行）")
        if ratio < 0.999:
            for l in difflib.unified_diff(want.splitlines(), got.splitlines(), "基准", "本次", lineterm="", n=0):
                print("   ", l)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
