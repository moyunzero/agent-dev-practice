"""第二轮对抗测试：覆盖悬空回退、目录链接语义和逐项解析异常。"""

from __future__ import annotations

import errno
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
    module_name = "s15_glob_boundary_adversarial_r2_module"
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


def test_glob_dangling_chains_preserve_boundary_before_limit(
    monkeypatch, tmp_path: Path
) -> None:
    """攻击悬空回退：经目录链接解析的内外悬空项和双节点环不能扰乱二十条限额。"""

    s15 = load_s15(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "inner").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = workspace.resolve()
    monkeypatch.setattr(s15, "WORKDIR", workspace)
    make_symlink("inner", workspace / "inside_alias", is_directory=True)
    make_symlink(outside, workspace / "outside_alias", is_directory=True)

    inside_names = [f"entry_zz_in_{index:02d}" for index in range(25)]
    for index in reversed(range(25)):
        make_symlink(
            f"outside_alias/missing_{index:02d}",
            workspace / f"entry_aa_out_{index:02d}",
        )
        make_symlink(
            f"inside_alias/missing_{index:02d}",
            workspace / inside_names[index],
        )
    make_symlink("entry_ab_loop_b", workspace / "entry_ab_loop_a")
    make_symlink("entry_ab_loop_a", workspace / "entry_ab_loop_b")

    # 悬空链接是否可读取与是否越界是两件事；内侧悬空项应保持原有列出行为。
    inside_error = s15.run_read(inside_names[0])
    assert inside_error.startswith("Error:")
    assert inside_error != "Error: path escapes workspace"
    assert s15.run_read("entry_aa_out_00") == "Error: path escapes workspace"
    assert s15.run_glob("entry_*") == "\n".join(inside_names[:20])
    assert s15.run_glob("entry_aa_out_*") == "(no matches)"
    assert s15.run_glob("entry_ab_loop_*") == "(no matches)"


def test_glob_directory_links_resolve_before_parent_components(
    monkeypatch, tmp_path: Path
) -> None:
    """攻击词法归一化：目录链接后的父目录分量必须按真实目标解析，并允许回到工作区。"""

    s15 = load_s15(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    (workspace / "subdir").mkdir(parents=True)
    outside = tmp_path / "outside"
    (outside / "deep").mkdir(parents=True)
    workspace = workspace.resolve()
    monkeypatch.setattr(s15, "WORKDIR", workspace)
    (workspace / "note.txt").write_text("内部", encoding="utf-8")
    (workspace / "subdir" / "util.txt").write_text("子目录", encoding="utf-8")
    (outside / "note.txt").write_text("外部", encoding="utf-8")
    (outside / "deep" / "other.txt").write_text("外部子目录", encoding="utf-8")
    make_symlink("subdir", workspace / "inside_alias", is_directory=True)
    make_symlink("../outside/deep", workspace / "outside_alias", is_directory=True)

    assert s15.run_read("inside_alias/util.txt") == "子目录"
    assert s15.run_glob("inside_alias/*") == "util.txt"
    assert s15.run_glob("inside_alias") == "inside_alias"
    assert s15.run_read("outside_alias/other.txt") == "Error: path escapes workspace"
    assert s15.run_glob("outside_alias/*") == "(no matches)"
    assert s15.run_glob("outside_alias") == "(no matches)"

    # 同样的父目录分量，经内侧和外侧链接后到达的位置不同。
    assert s15.run_read("inside_alias/../note.txt") == "内部"
    assert s15.run_glob("inside_alias/../*.txt") == "note.txt"
    assert s15.run_read("outside_alias/../note.txt") == "Error: path escapes workspace"
    assert s15.run_glob("outside_alias/../*.txt") == "(no matches)"

    # 判定最终位置，不能仅因途中经过外侧链接就拒绝已经回到工作区的结果。
    assert s15.run_read("outside_alias/../../workspace/note.txt") == "内部"
    assert s15.run_glob("outside_alias/../../workspace/*.txt") == "note.txt"


@pytest.mark.parametrize("phase", ["strict", "fallback"])
@pytest.mark.parametrize(
    "error_type",
    [PermissionError, OSError, RuntimeError],
    ids=["permission", "oserror", "runtime"],
)
def test_glob_resolution_errors_are_isolated_per_match(
    monkeypatch, tmp_path: Path, phase: str, error_type: type[Exception]
) -> None:
    """攻击异常作用域：严格解析或悬空回退报错时，前后异常项都不能清空或截短合法结果。"""

    s15 = load_s15(monkeypatch, tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    workspace = workspace.resolve()
    monkeypatch.setattr(s15, "WORKDIR", workspace)
    valid_names = [f"file_{index:02d}.txt" for index in range(25)]
    invalid_names = ("aa_unresolved.txt", "zz_unresolved.txt")
    for name in reversed(valid_names + list(invalid_names)):
        (workspace / name).write_text("内容", encoding="utf-8")

    original_resolve = Path.resolve

    def resolve_with_error(path: Path, strict: bool = False) -> Path:
        """只向指定候选注入解析异常，其余路径使用真实文件系统。"""

        if path.parent == workspace and path.name in invalid_names:
            if phase == "fallback" and strict:
                raise FileNotFoundError(errno.ENOENT, "模拟悬空链接")
            if error_type is PermissionError:
                raise PermissionError(errno.EACCES, "模拟权限错误")
            if error_type is OSError:
                raise OSError(errno.ELOOP, "模拟无法解析的路径")
            raise RuntimeError("模拟旧版符号链接环")
        return original_resolve(path, strict=strict)

    # 使用定点故障注入，避免权限测试受管理员身份或文件系统权限模型影响。
    monkeypatch.setattr(Path, "resolve", resolve_with_error)
    assert s15.run_glob("*") == "\n".join(valid_names[:20])
    assert s15.run_glob("aa_unresolved.txt") == "(no matches)"
    assert s15.run_glob("zz_unresolved.txt") == "(no matches)"
