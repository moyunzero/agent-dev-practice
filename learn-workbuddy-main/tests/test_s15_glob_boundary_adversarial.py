"""对抗测试：固定 s15 的逐项边界过滤及其结果保留规则。"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_s15(monkeypatch, tmp_path: Path):
    """使用离线 stub 导入教学模块，状态目录放进临时目录。"""

    monkeypatch.syspath_prepend(str(ROOT / "tests" / "stubs"))
    monkeypatch.setenv("MODEL_ID", "offline-test-model")
    monkeypatch.setenv("WORKBUDDY_HOME", str(tmp_path / "state"))
    saved_anthropic = sys.modules.pop("anthropic", None)
    module_name = "s15_glob_boundary_adversarial_module"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / "s15_prompt_assembly" / "code.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, module_name, module)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop("anthropic", None)
        if saved_anthropic is not None:
            sys.modules["anthropic"] = saved_anthropic
    return module


def make_symlink(target, link: Path, *, is_directory: bool = False) -> None:
    """只在平台没有符号链接能力或创建权限时跳过。"""

    if not hasattr(os, "symlink"):
        pytest.skip("当前平台不支持符号链接")
    try:
        os.symlink(target, link, target_is_directory=is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"当前环境无法创建符号链接：{exc}")


@pytest.mark.parametrize("loop_name", ["aa_loop", "zz_loop"])
def test_glob_keeps_valid_matches_when_one_symlink_loops(
    monkeypatch, tmp_path: Path, loop_name: str
) -> None:
    """攻击逐项解析异常：排序靠前或二十条之后的链接环都不能中断合法结果。"""

    s15 = load_s15(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workspace = workspace.resolve()
    monkeypatch.setattr(s15, "WORKDIR", workspace)
    names = [f"file_{index:02d}.txt" for index in range(25)]
    for name in reversed(names):
        (workspace / name).write_text("内容", encoding="utf-8")
    make_symlink(loop_name, workspace / loop_name)

    # 解析失败的单项应被排除，其他可读取项仍按原格式排序并限为二十条。
    assert s15.run_read(names[0]) == "内容"
    assert s15.run_read(loop_name).startswith("Error:")
    assert s15.run_glob("*") == "\n".join(names[:20])
    assert s15.run_glob(loop_name) == "(no matches)"


def test_glob_filters_before_sorting_and_limiting(monkeypatch, tmp_path: Path) -> None:
    """攻击先截断再过滤：前二十五个外部结果不能挤掉后面的工作区内结果。"""

    s15 = load_s15(monkeypatch, tmp_path)
    root = tmp_path / "layout"
    outside = root / "aa_outside"
    workspace = root / "zz_workspace"
    outside.mkdir(parents=True)
    workspace.mkdir()
    workspace = workspace.resolve()
    monkeypatch.setattr(s15, "WORKDIR", workspace)
    names = [f"file_{index:02d}.txt" for index in range(25)]
    for index in reversed(range(25)):
        (outside / f"outside_{index:02d}.txt").write_text("外部", encoding="utf-8")
        (workspace / names[index]).write_text("内部", encoding="utf-8")

    assert s15.run_read("../aa_outside/outside_00.txt") == "Error: path escapes workspace"
    assert s15.run_glob("../*/*") == "\n".join(names[:20])
    assert s15.run_glob("../*") == workspace.name


@pytest.mark.parametrize("workspace_name", ["项目[2026]", "workspace*?"])
def test_glob_escapes_only_workspace_prefix(
    monkeypatch, tmp_path: Path, workspace_name: str
) -> None:
    """攻击前缀与模式混淆：工作区元字符应按字面量处理，调用方字符组仍须生效。"""

    s15 = load_s15(monkeypatch, tmp_path)
    if os.name == "nt" and any(char in workspace_name for char in "*?"):
        pytest.skip("当前平台的目录名不支持这些字符")
    workspace = tmp_path / workspace_name
    workspace.mkdir()
    workspace = workspace.resolve()
    monkeypatch.setattr(s15, "WORKDIR", workspace)
    for name in ("main.py", "notes.py", "util.py"):
        (workspace / name).write_text("内容", encoding="utf-8")

    assert s15.run_glob("[mn]*.py") == "main.py\nnotes.py"
    assert s15.run_glob("*.py") == "main.py\nnotes.py\nutil.py"


@pytest.mark.parametrize("workdir_kind", ["symlink", "parent_component"])
def test_glob_uses_the_same_unresolved_workdir_as_read(
    monkeypatch, tmp_path: Path, workdir_kind: str
) -> None:
    """攻击另行解析基准：非规范化 WORKDIR 的判定必须与本章读取工具一致。"""

    s15 = load_s15(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workspace = workspace.resolve()
    (workspace / "main.py").write_text("内容", encoding="utf-8")
    if workdir_kind == "symlink":
        workdir = workspace.parent / "alias"
        make_symlink(workspace, workdir, is_directory=True)
    else:
        workdir = workspace / ".." / workspace.name
    monkeypatch.setattr(s15, "WORKDIR", workdir)

    # 固定本卡指定的比较基准；若要接受这些路径，应另行同时调整两个工具。
    assert s15.run_read("main.py") == "Error: path escapes workspace"
    assert s15.run_glob("*.py") == "(no matches)"
