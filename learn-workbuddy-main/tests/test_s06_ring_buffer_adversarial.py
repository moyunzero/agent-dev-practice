"""对抗性检查环形缓冲区的字节顺序、回绕解码和残缺序列。"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections import deque
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s06():
    """用独立模块名离线导入章节，并恢复导入前的环境与 SDK。"""
    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    saved_environ = os.environ.copy()
    os.environ["MODEL_ID"] = "offline-test-model"
    module_name = "s06_ring_buffer_adversarial_module"
    try:
        spec = importlib.util.spec_from_file_location(
            module_name,
            ROOT / "s06_sidecar_server" / "code.py",
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.path.remove(str(stub_dir))
        sys.modules.pop(module_name, None)
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
        os.environ.clear()
        os.environ.update(saved_environ)


@pytest.mark.parametrize("offset", range(11))
def test_mixed_width_text_at_every_write_position(s06, offset: int) -> None:
    """穷举写指针位置，攻击完整的二、三、四字节字符在物理边界被拆开。"""
    text = "Aé中😀Z"  # 一、二、三、四字节字符混排，共十一字节
    ring = s06.RingBuffer(size=11)
    ring.write("x" * offset)
    ring.write(text)

    assert ring.is_full
    assert ring.write_pos == offset
    assert ring.total_written == 11 + offset
    assert ring.used == 11
    assert ring.read_all() == "Aé中😀Z"
    assert ring.read_all() == "Aé中😀Z"  # 重复读取不得改变缓冲区


@pytest.mark.parametrize(
    ("remaining", "expected"),
    [
        (1, "\ufffd文"),
        (2, "\ufffd\ufffd文"),
        (3, "\ufffd\ufffd\ufffd文"),
    ],
)
def test_oldest_emoji_continuations_are_not_discarded(
    s06, remaining: int, expected: str
) -> None:
    """攻击残缺 emoji 的一至三个续字节被丢弃、合并替换或连带读坏新字符。"""
    ring = s06.RingBuffer(size=remaining + 3)
    ring.write("😀文")

    assert ring.is_full
    assert ring.total_written == 7
    assert ring.write_pos == 7 % ring.size
    assert ring.read_all() == expected


@pytest.mark.parametrize("size", range(1, 13))
def test_fragmented_bytes_match_independent_fifo(s06, size: int) -> None:
    """用逐字节先进先出模型攻击多圈覆盖、分块字符、未写满读取与空写状态。"""
    ring = s06.RingBuffer(size=size)
    recent = deque()
    total = 0
    chunks = [
        b"",
        "Aé中😀Z",
        b"",
        b"\xf0",
        b"\x9f",
        b"\x98",
        b"\x80",
        b"\xff\xe2",
        b"(",
        b"\xa1",
        "文éQ",
        bytes(range(128, 144)),
        b"",
    ]

    assert ring.read_all() == ""
    assert ring.write_pos == ring.total_written == ring.used == 0
    assert not ring.is_full
    for chunk in chunks:
        ring.write(chunk)
        data = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
        # 模型只从队尾加入、队首淘汰，不读取实现的物理存储或写指针。
        for byte in data:
            recent.append(byte)
            if len(recent) > size:
                recent.popleft()
            total += 1
        expected = bytes(recent).decode("utf-8", errors="replace")
        assert ring.total_written == total
        assert ring.write_pos == total % size
        assert ring.used == len(recent)
        assert ring.is_full == (total >= size)
        assert len(ring.buffer) == size
        assert ring.read_all() == expected
        assert ring.read_all() == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"\xe2(\xa1Z", "\ufffd(\ufffdZ"),
        (b"\xf0\x9fZ", "\ufffdZ"),
        (b"\xed\xa0\x80Z", "\ufffd\ufffd\ufffdZ"),
        (b"\xc0\xaf\xf0\x9f\x98\x80", "\ufffd\ufffd😀"),
    ],
)
def test_malformed_utf8_at_every_rotation(
    s06, payload: bytes, expected: str
) -> None:
    """攻击非法序列跨物理边界时的错误分组，以及过滤替换字符误删真实数据。"""
    for offset in range(len(payload)):
        ring = s06.RingBuffer(size=len(payload))
        ring.write(b"x" * offset)
        ring.write(payload)

        assert ring.is_full
        assert ring.write_pos == offset
        # 字面值区分孤立续字节与不完整的合法前缀，不能按每个非法字节替换。
        assert ring.read_all() == expected
