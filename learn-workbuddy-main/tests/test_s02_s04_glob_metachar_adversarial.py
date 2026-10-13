"""对抗测试：验证两章的工作区转义、匹配边界及原有执行语义。"""

from __future__ import annotations

import glob
import importlib.util
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = ["s02_tool_dispatch", "s04_permission_hooks"]


def load_chapter(monkeypatch, chapter: str):
    """按已有复现测试的方式，用离线桩加载章节。"""

    stub_dir = ROOT / "tests" / "stubs"
    monkeypatch.syspath_prepend(str(stub_dir))
    monkeypatch.setenv("MODEL_ID", "offline-test-model")
    saved_anthropic = sys.modules.pop("anthropic", None)

    module_name = f"{chapter}_glob_metachar_adversarial_module"
    spec = importlib.util.spec_from_file_location(
        module_name, ROOT / chapter / "code.py"
    )
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


def make_workspace(monkeypatch, module, tmp_path: Path, name: str) -> Path:
    """在临时目录创建工作区，保持生产代码已解析根路径的约定。"""

    workspace = tmp_path / name
    workspace.mkdir()
    monkeypatch.setattr(module, "WORKDIR", workspace.resolve())
    return workspace.resolve()


@pytest.mark.parametrize("chapter", CHAPTERS)
@pytest.mark.parametrize(
    "workspace_name",
    ["star*", "question?", "deny[!ab]", "open[", "]start", "mixed[*?]"],
)
def test_workspace_metacharacters_are_literal(
    monkeypatch, tmp_path: Path, chapter: str, workspace_name: str
) -> None:
    """攻击仅处理成对方括号或把模型字符类一起转义的实现。"""

    module = load_chapter(monkeypatch, chapter)
    workspace = make_workspace(monkeypatch, module, tmp_path, workspace_name)
    for name in ("a.txt", "b.txt", "c.txt", "[ab].txt"):
        (workspace / name).write_text(name, encoding="utf-8")

    assert sorted(module.run_glob("[ab].txt").splitlines()) == ["a.txt", "b.txt"]
    assert sorted(module.run_glob("?.txt").splitlines()) == [
        "a.txt", "b.txt", "c.txt"
    ]


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_recursive_depth_is_chapter_specific(
    monkeypatch, tmp_path: Path, chapter: str
) -> None:
    """攻击把两章统一设为递归，或让第二章丢失递归能力的实现。"""

    module = load_chapter(monkeypatch, chapter)
    workspace = make_workspace(monkeypatch, module, tmp_path, "项目[2026]")
    paths = ("main.py", "src/one.py", "src/deep/two.py")
    for relative in paths:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x = 1\n", encoding="utf-8")

    expected = paths if chapter == "s02_tool_dispatch" else ("src/one.py",)
    assert set(module.run_glob("**/*.py").splitlines()) == {
        str(Path(relative)) for relative in expected
    }


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_trailing_separator_matches_only_directories(
    monkeypatch, tmp_path: Path, chapter: str
) -> None:
    """攻击拼接时吞掉末尾分隔符，导致目录模式错误匹配普通文件。"""

    module = load_chapter(monkeypatch, chapter)
    workspace = make_workspace(monkeypatch, module, tmp_path, "项目[2026]")
    (workspace / "file.txt").write_text("内容", encoding="utf-8")
    (workspace / "folder").mkdir()

    assert module.run_glob("file.txt/") == "(no matches)"
    assert module.run_glob("*/") == "folder"
    assert module.run_glob("folder/") == "folder"


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_glob_filters_outside_matches_and_symlinks(
    monkeypatch, tmp_path: Path, chapter: str
) -> None:
    """攻击绝对模式丢弃前缀、同名前缀兄弟目录及符号链接逃逸。"""

    module = load_chapter(monkeypatch, chapter)
    workspace = make_workspace(monkeypatch, module, tmp_path, "项目[2026]")
    outside = tmp_path / "项目[2026]-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("外部内容", encoding="utf-8")
    (workspace / "safe.txt").write_text("内部内容", encoding="utf-8")
    (workspace / "inside.txt").symlink_to(workspace / "safe.txt")
    (workspace / "escape").symlink_to(outside, target_is_directory=True)

    assert module.run_glob("inside.txt") == "safe.txt"
    patterns = (
        f"../{glob.escape(outside.name)}/*.txt",
        glob.escape(str(outside.resolve())) + "/*.txt",
        "escape/*.txt",
    )
    for pattern in patterns:
        assert module.run_glob(pattern) == "(no matches)", pattern


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_glob_does_not_change_process_directory(
    monkeypatch, tmp_path: Path, chapter: str
) -> None:
    """攻击借助切换进程目录实现匹配的做法，包括切换后恢复目录。"""

    module = load_chapter(monkeypatch, chapter)
    workspace = make_workspace(monkeypatch, module, tmp_path, "项目[2026]")
    (workspace / "main.py").write_text("x = 1\n", encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    original_cwd = Path.cwd()

    def reject_chdir(*args, **kwargs):
        """禁止匹配期间改变进程共享的当前目录。"""
        pytest.fail("glob 匹配不得改变进程当前目录")

    # 保留真实工作目录恢复能力，仅在调用期间拦截切换操作。
    with monkeypatch.context() as guard:
        guard.setattr(os, "chdir", reject_chdir)
        assert module.run_glob("*.py") == "main.py"
        assert Path.cwd() == original_cwd


@pytest.mark.parametrize("chapter", CHAPTERS)
def test_absolute_patterns_keep_glob_semantics(
    monkeypatch, tmp_path: Path, chapter: str
) -> None:
    """攻击重复转义模型绝对模式，或把模式中的字符类擅自当作字面量。"""

    module = load_chapter(monkeypatch, chapter)
    workspace = make_workspace(monkeypatch, module, tmp_path, "项目[2026]")
    for name in ("a.txt", "b.txt", "c.txt"):
        (workspace / name).write_text(name, encoding="utf-8")

    # 直接验证处理函数；第四章的权限前置检查另有独立职责。
    escaped_prefix = glob.escape(str(workspace))
    pattern = escaped_prefix + "/[ab].txt"
    assert sorted(module.run_glob(pattern).splitlines()) == ["a.txt", "b.txt"]
    assert module.run_glob(str(workspace / "a.txt")) == "(no matches)"
