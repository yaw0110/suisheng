"""断句单元测试（不加载模型）。运行：.venv/bin/python -I tests/test_segmenter.py"""
from livecaption.segmenter import SegParams, Token, find_splits, forced_split, plan_splits

P = SegParams()


def toks(spec):
    """spec: [(文字, 起始秒, 标点)]"""
    return [Token(t, ts, p) for t, ts, p in spec]


def test_split_after_sentence_end():
    # 「好唔好？」后停 0.6s 再说话：句末标点阈值 0.3 → 应断开
    t = toks([("你", 0.0, 0), ("好", 0.2, 0), ("唔", 0.4, 0), ("好", 0.6, 2), ("我", 1.4, 0), ("哋", 1.6, 0)])
    pts = find_splits(t, 2.0, P)
    assert [i for i, _ in pts] == [3], pts
    assert 0.6 < pts[0][1] < 1.4                     # 切点落在停顿里


def test_no_split_inside_normal_speech():
    t = toks([(c, i * 0.22, 0) for i, c in enumerate("今天我们来聊一聊人工智能")])
    assert find_splits(t, len(t) * 0.22 + 0.1, P) == []


def test_short_fragment_not_split():
    # 只有 2 个字后的普通停顿（< long_pause）不单独成句
    t = toks([("哎", 0.0, 0), ("呀", 0.2, 1), ("你", 1.0, 0), ("做", 1.2, 0), ("乜", 1.4, 0), ("嘢", 1.6, 0)])
    assert find_splits(t, 1.9, P) == []


def test_tail_pause_finalizes():
    # 句尾停够了（> 阈值+0.2）→ 最后一个字也断开
    t = toks([(c, i * 0.2, 0) for i, c in enumerate("我哋听日去旺角行街")])
    pts = find_splits(t, t[-1].ts + 1.5, P)
    assert pts and pts[-1][0] == len(t) - 1


def test_forced_split_prefers_period():
    t = toks([("一", 0.0, 0), ("二", 0.3, 0), ("三", 0.6, 0), ("四", 0.9, 2), ("五", 1.2, 0), ("六", 1.5, 1),
              ("七", 1.8, 0), ("八", 2.1, 0), ("九", 2.4, 0)])
    (i, cut), = forced_split(t, P)
    assert i == 3 and 0.9 < cut < 1.2


def test_plan_forces_when_too_long():
    t = toks([(c, i * 0.25, 2 if i == 20 else 0) for i, c in enumerate("字" * 44)])
    assert plan_splits(t, 11.0, P)                   # 超过 max_sentence=10s 必须切


if __name__ == "__main__":
    n = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); n += 1; print("ok", name)
    print(f"{n} 个断句测试全部通过")
