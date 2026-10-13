"""复现测试：s02 / s04 的 glob 工具在工作区路径含方括号时找不到任何文件。

两章的 run_glob() 都把工作区绝对路径和模型给的 pattern 直接拼成一个 glob
表达式，工作区路径里的 "[" "]" 会被当成字符类解释。于是在 "项目[2026]"
这样的目录里，glob("*.py") 永远返回 "(no matches)"，而同一工作区里的
read_file 却能正常读到文件。glob 的契约是“在工作区里按 pattern 找文件”：
通配符只应该来自模型给的 pattern，不应该来自工作区路径本身。

对照用例同时保证修复只转义工作区前缀：模型自己写的 "[ab].txt"、"?.txt"
仍然按通配符匹配。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = ["s02_tool_dispatch", "s04_permission_hooks"]
BRACKET_WORKSPACES = ["项目[2026]", "release[v1]"]


def load_chapter(monkeypatch, chapter: str):
    """使用离线 Anthropic stub 导入独立的教学模块（与 test_s02_tool_dispatch 一致）。"""

    stub_dir = ROOT / "tests" / "stubs"
    monkeypatch.syspath_prepend(str(stub_dir))
    monkeypatch.setenv("MODEL_ID", "offline-test-model")
    saved_anthropic = sys.modules.pop("anthropic", None)

    module_name = f"{chapter}_glob_metachar_test_module"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / chapter / "code.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
    return module


def make_workspace(monkeypatch, module, root: Path, name: str) -> Path:
    """建一个小工作区并让模块的 WORKDIR 指向它。"""

    workspace = root / name
    (workspace / "src").mkdir(parents=True)
    (workspace / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (workspace / "src" / "工具.py").write_text("x = 1\n", encoding="utf-8")
    for stem in ("a", "b", "c"):
        (workspace / f"{stem}.txt").write_text(stem, encoding="utf-8")
    monkeypatch.setattr(module, "WORKDIR", workspace.resolve())
    return workspace


def glob_lines(module, pattern: str) -> list[str]:
    # s04 的 run_glob 不排序，这里统一排序后再比较。
    return sorted(module.run_glob(pattern).splitlines())


@pytest.mark.parametrize("workspace_name", BRACKET_WORKSPACES)
@pytest.mark.parametrize("chapter", CHAPTERS)
def test_glob_finds_files_when_workspace_path_contains_brackets(
    monkeypatch,
    tmp_path: Path,
    chapter: str,
    workspace_name: str,
) -> None:
    module = load_chapter(monkeypatch, chapter)
    make_workspace(monkeypatch, module, tmp_path, workspace_name)

    # 对照组：同一个工作区里 read_file 正常，说明路径边界本身没有问题。
    assert module.run_read("main.py") == "print('hi')"

    # 期望：按 pattern 在工作区内匹配；实际（bug）：返回 "(no matches)"。
    top_level = glob_lines(module, "*.py")
    assert top_level == ["main.py"], (
        f"{chapter} 在工作区 {workspace_name!r} 下 glob('*.py') 应找到 main.py，实际返回：{top_level!r}"
    )
    nested = glob_lines(module, "**/*.py")
    assert "src/工具.py" in nested, (
        f"{chapter} 在工作区 {workspace_name!r} 下 glob('**/*.py') 应找到 src/工具.py，实际返回：{nested!r}"
    )


@pytest.mark.parametrize("workspace_name", ["plain_workspace", "项目[2026]"])
@pytest.mark.parametrize("chapter", CHAPTERS)
def test_model_pattern_wildcards_are_not_escaped(
    monkeypatch,
    tmp_path: Path,
    chapter: str,
    workspace_name: str,
) -> None:
    """对照用例：修复只能转义工作区前缀，模型 pattern 里的字符类和 ? 仍是通配符。

    普通工作区在 main 上就应通过（防止修复把 pattern 也转义掉）；
    带方括号的工作区在 main 上因本 bug 失败，修复后应通过。
    """

    module = load_chapter(monkeypatch, chapter)
    make_workspace(monkeypatch, module, tmp_path, workspace_name)

    char_class = glob_lines(module, "[ab].txt")
    single_char = glob_lines(module, "?.txt")

    assert char_class == ["a.txt", "b.txt"], (
        f"{chapter} 在工作区 {workspace_name!r} 下 glob('[ab].txt') 应按字符类匹配，实际返回：{char_class!r}"
    )
    assert single_char == ["a.txt", "b.txt", "c.txt"], (
        f"{chapter} 在工作区 {workspace_name!r} 下 glob('?.txt') 应匹配单字符文件名，实际返回：{single_char!r}"
    )
