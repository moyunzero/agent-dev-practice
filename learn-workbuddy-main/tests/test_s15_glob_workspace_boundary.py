"""复现测试：s15 的 glob 工具与同一节的 read_file 边界不一致。

s15 的 "Tools (simplified)" 里，run_read() 把路径 resolve 后与 WORKDIR 比较，
越界返回 "Error: path escapes workspace"；s02 / s04 的 run_glob() 也都用
is_relative_to(WORKDIR) 过滤结果。但 s15 的 run_glob() 直接
glob(str(WORKDIR / pattern))，没有这一步过滤，"../*" 或绝对路径 pattern
会列出工作区外的文件名。修复目标是让 glob 采用与 run_read() 相同的边界。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_s15(monkeypatch, tmp_path: Path):
    """使用离线 stub 导入教学模块，状态目录放进 tmp_path。"""

    stub_dir = ROOT / "tests" / "stubs"
    monkeypatch.syspath_prepend(str(stub_dir))
    monkeypatch.setenv("MODEL_ID", "offline-test-model")
    monkeypatch.setenv("WORKBUDDY_HOME", str(tmp_path / "state"))
    saved_anthropic = sys.modules.pop("anthropic", None)

    module_name = "s15_glob_traversal_test_module"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "s15_prompt_assembly" / "code.py")
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


def make_layout(monkeypatch, module, tmp_path: Path, workspace_name: str) -> Path:
    """工作区内放两个文件，工作区外放一个文件和一个目录，并把 WORKDIR 指向工作区。"""

    root = tmp_path / "layout"
    workspace = root / workspace_name
    (workspace / "src").mkdir(parents=True)
    (workspace / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (workspace / "src" / "util.py").write_text("x = 1\n", encoding="utf-8")
    (root / "outside.txt").write_text("outside", encoding="utf-8")
    (root / "outside_dir").mkdir()
    (root / "outside_dir" / "note.txt").write_text("note", encoding="utf-8")
    monkeypatch.setattr(module, "WORKDIR", workspace.resolve())
    return workspace


OUTSIDE_NAMES = ("outside.txt", "outside_dir", "note.txt")


@pytest.mark.parametrize("pattern", ["../*", "../outside_dir/*", "{outside_abs}/*"])
def test_glob_does_not_list_files_outside_workspace(monkeypatch, tmp_path: Path, pattern: str) -> None:
    s15 = load_s15(monkeypatch, tmp_path)
    workspace = make_layout(monkeypatch, s15, tmp_path, "workspace")
    template = pattern
    pattern = template.format(outside_abs=(workspace.parent / "outside_dir").resolve())

    # 对照：同一节的 read_file 会拒绝同样越界的路径。
    assert s15.run_read("../outside.txt") == "Error: path escapes workspace"

    result = s15.run_glob(pattern)

    # 期望：与 read_file 边界一致，不列出工作区外的文件名；
    # 实际（bug）：列出了工作区外的文件名。
    listed = [name for name in OUTSIDE_NAMES if name in result.splitlines()]
    assert not listed, f"glob({template!r}) 列出了工作区外的文件名 {listed}，完整输出：{result!r}"


def test_glob_parent_pattern_returns_only_workspace_itself(monkeypatch, tmp_path: Path) -> None:
    """固定 "../*" 修复后的完整输出：只剩工作区目录本身的名字。

    工作区根目录 resolve 后等于 WORKDIR，不算越界，所以保留；输出格式仍是
    “只给文件名”，因此是 "workspace"（s02 这里输出相对路径 "."）。
    """

    s15 = load_s15(monkeypatch, tmp_path)
    make_layout(monkeypatch, s15, tmp_path, "workspace")

    result = s15.run_glob("../*")

    assert result == "workspace", f"glob('../*') 修复后应只返回 'workspace'，实际返回：{result!r}"


def test_glob_matches_read_file_for_symlink_pointing_outside(monkeypatch, tmp_path: Path) -> None:
    """工作区内指向外部目录的符号链接：glob 与 read_file 一样按 resolve 后的位置判断。

    read_file 对 "link/note.txt" 返回越界错误，所以 glob 也不应列出 link 本身或
    link 下的文件。这是修复后有意的行为变化（修复前 "*" 会列出 link）。
    """

    if sys.platform == "win32":
        pytest.skip("Windows 上创建符号链接通常需要额外权限")
    s15 = load_s15(monkeypatch, tmp_path)
    workspace = make_layout(monkeypatch, s15, tmp_path, "workspace")
    try:
        os.symlink(workspace.parent / "outside_dir", workspace / "link", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"当前环境不支持符号链接：{exc}")

    # 对照：read_file 把指向外部的符号链接视为越界（main 上就是如此）。
    assert s15.run_read("link/note.txt") == "Error: path escapes workspace"

    top_level = s15.run_glob("*")
    through_link = s15.run_glob("link/*")

    assert top_level == "main.py\nsrc", (
        f"glob('*') 应与 read_file 一致，不列出指向工作区外的 link，实际返回：{top_level!r}"
    )
    assert through_link == "(no matches)", (
        f"glob('link/*') 应与 read_file 一致，不列出 link 指向的外部文件，实际返回：{through_link!r}"
    )


@pytest.mark.parametrize("workspace_name", ["workspace", "项目[2026]"])
def test_glob_inside_workspace_still_matches(monkeypatch, tmp_path: Path, workspace_name: str) -> None:
    """对照用例：修复后工作区内的正常 glob 不受影响，输出格式（只给文件名）保持不变。

    普通工作区在 main 上就应通过；带方括号的工作区在 main 上因工作区前缀未转义
    （与 #4 同一根因）而失败，按本卡设计修复后应通过。
    """

    s15 = load_s15(monkeypatch, tmp_path)
    make_layout(monkeypatch, s15, tmp_path, workspace_name)

    for pattern, expected in [("*.py", "main.py"), ("src/*.py", "util.py"), ("[ms]*", "main.py\nsrc")]:
        result = s15.run_glob(pattern)
        assert result == expected, (
            f"工作区 {workspace_name!r} 下 glob({pattern!r}) 应返回 {expected!r}，实际返回：{result!r}"
        )
