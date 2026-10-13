"""s06 RingBuffer 回绕后读出的近期日志不应损坏多字节字符。

README 说 RingBuffer「满了就覆盖最旧的数据——保留最近的日志」，
`read_all()` 的 docstring 也写明按「最旧到最新」的顺序读出全部有效数据。

当前实现在缓冲区写满后，把 `buffer[write_pos:]` 和 `buffer[:write_pos]`
分两段各自 UTF-8 解码再拼接。物理回绕点 `write_pos` 可能正好落在一个中文字符
的字节中间，这个字符就会被拆成两半、各自变成替换字符，而它可能是最新写入的内容。

期望值的定义：缓冲区写满后保留的是「最近写入的 size 个字节」，读出结果应等于
把这些字节按最旧到最新拼好后整体 `decode("utf-8", errors="replace")`。
因此只有最旧的、被覆盖掉一部分的那个字符会变成替换字符（不静默丢弃），
完整保存的字符必须原样读出。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def s06():
    """用离线 anthropic stub 导入 s06 章节代码。

    s06 模块级只有常量定义和 `load_dotenv()`，不起 socket / 线程（demo 在
    `if __name__ == "__main__"` 之后）。这里仍整体快照并恢复 `os.environ`，
    并用独立的模块名、用完即从 `sys.modules` 移除，不影响其他测试。
    """

    stub_dir = ROOT / "tests" / "stubs"
    sys.path.insert(0, str(stub_dir))
    saved_anthropic = sys.modules.pop("anthropic", None)
    saved_environ = os.environ.copy()
    os.environ["MODEL_ID"] = "offline-test-model"
    module_name = "s06_ring_buffer_utf8_wrap_test_module"
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


def expected_tail(writes: list[str], size: int) -> str:
    """缓冲区应保留的内容：最近 size 个字节，整体按 errors='replace' 解码。"""
    data = "".join(writes).encode("utf-8")
    return data[-size:].decode("utf-8", errors="replace")


def fill(s06, size: int, writes: list[str]):
    ring = s06.RingBuffer(size=size)
    for chunk in writes:
        ring.write(chunk)
    return ring


@pytest.mark.parametrize(
    ("size", "writes", "write_pos", "expected"),
    [
        # "ab" + "中文" 共 8 字节，保留的正好是完整的「中文」，回绕点在「文」第 1、2 字节之间。
        (6, ["ab", "中文"], 2, "中文"),
        # "a" + "中文" 共 7 字节，回绕点在「中」第 1、2 字节之间。
        (6, ["a", "中文"], 1, "中文"),
        # 回绕点在「日」中间，且保留内容前后都有 ASCII。
        (8, ["xxxxx", "a日志b"], 5, "a日志b"),
    ],
    ids=["wrap-in-2nd-char", "wrap-in-1st-char", "wrap-in-cjk-amid-ascii"],
)
def test_multibyte_char_across_physical_wrap_survives(
    s06, size: int, writes: list[str], write_pos: int, expected: str
) -> None:
    ring = fill(s06, size, writes)

    assert ring.is_full
    assert ring.write_pos == write_pos  # 确认物理回绕点确实落在多字节字符中间
    assert expected == expected_tail(writes, size)
    assert ring.read_all() == expected, f"缓冲区里完整保留的最近数据被读坏：{ring.read_all()!r}"


def test_oldest_partial_char_becomes_replacement_and_newest_is_exact(s06) -> None:
    # size=5 写「中文」(6 字节)：最旧的「中」被覆盖掉 1 个字节，剩下的 2 个续字节
    # 各自解码成 1 个替换字符（不静默丢弃），完整保存的「文」原样读出。
    ring = fill(s06, 5, ["中文"])

    assert ring.write_pos == 1
    assert expected_tail(["中文"], 5) == "\ufffd\ufffd文"
    assert ring.read_all() == "\ufffd\ufffd文", f"最新写入的字符被读坏：{ring.read_all()!r}"


@pytest.mark.parametrize(
    ("size", "writes", "expected"),
    [
        # 写入总量正好等于 size：total_written == size，走写满分支，write_pos == 0。
        (6, ["中文"], "中文"),
        # 回绕一整圈后又正好落在 size 的整数倍：write_pos == 0，保留最新一圈。
        (6, ["中文", "日志"], "日志"),
    ],
    ids=["total-equals-size", "total-equals-2x-size"],
)
def test_write_pos_zero_after_exact_multiple_reads_like_unwrapped(
    s06, size: int, writes: list[str], expected: str
) -> None:
    # 边界对照：write_pos == 0 时 buffer[0:] + buffer[:0] 就是整段，main 上也通过；
    # 修复后不能因为改动写满分支而变坏。
    ring = fill(s06, size, writes)

    assert ring.is_full
    assert ring.write_pos == 0
    assert ring.read_all() == expected == expected_tail(writes, size)


def test_unwrapped_multibyte_text_reads_back(s06) -> None:
    # 对照：没写满时只有一段解码，main 上就正常。
    ring = fill(s06, 16, ["日志：中文"])

    assert not ring.is_full
    assert ring.read_all() == "日志：中文"


def test_ascii_wrap_keeps_newest_bytes_in_order(s06) -> None:
    # 对照：单字节内容回绕后按「最旧到最新」读出，main 上就正常，修复后也不能变。
    ring = fill(s06, 4, ["abcdef"])

    assert ring.read_all() == "cdef"
    assert isinstance(ring.read_all(), str)
