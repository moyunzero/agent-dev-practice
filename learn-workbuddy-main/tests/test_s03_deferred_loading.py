"""Behavior tests for s03's discover -> load -> execute boundary."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load_s03():
    """Import the standalone offline lesson without running its CLI."""

    module_name = "s03_deferred_loading_test_module"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "s03_deferred_loading" / "code.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def deferred_schema(name: str, description: str) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        },
    }


def test_registry_rejects_duplicate_names() -> None:
    s03 = load_s03()
    registry = s03.ToolRegistry()
    schema = deferred_schema("echo", "Echo a value.")
    registry.register("echo", schema, lambda value: value, defer=True)

    with pytest.raises(ValueError, match="duplicate tool name: echo"):
        registry.register("echo", schema, lambda value: value, defer=True)


def test_search_miss_is_explicit_and_does_not_activate_a_tool() -> None:
    s03 = load_s03()
    registry = s03.ToolRegistry()
    registry.register(
        "image_edit",
        deferred_schema("image_edit", "Edit an image."),
        lambda value: value,
        defer=True,
    )

    result = registry.search(["calendar"], top_k=3)

    assert result.matches == ()
    assert result.missing == ("calendar",)
    assert registry.get_loaded_names() == ()
    assert "No deferred tools" not in result.render()
    assert "deferred tool not found" in result.render()


def test_equal_score_search_results_have_stable_name_order() -> None:
    s03 = load_s03()
    registry = s03.ToolRegistry()
    # Register in reverse alphabetical order to prove the tie-break is explicit,
    # rather than an accidental consequence of dictionary insertion order.
    registry.register(
        "zebra_image",
        deferred_schema("zebra_image", "Render an image."),
        lambda value: value,
        defer=True,
    )
    registry.register(
        "alpha_image",
        deferred_schema("alpha_image", "Render an image."),
        lambda value: value,
        defer=True,
    )

    first = registry.search(["image"], top_k=2)
    second = registry.search(["image"], top_k=2)

    assert [match.name for match in first.matches] == ["alpha_image", "zebra_image"]
    assert [match.name for match in second.matches] == ["alpha_image", "zebra_image"]
    assert all(match.cache_hit is False for match in first.matches)
    assert all(match.cache_hit is True for match in second.matches)


def test_deferred_tool_must_be_discovered_before_execution() -> None:
    s03 = load_s03()
    registry = s03.ToolRegistry()
    registry.register(
        "echo",
        deferred_schema("echo", "Echo a value."),
        lambda value: value.upper(),
        defer=True,
    )

    denied = s03.handle_defer_execute(registry, "echo", {"value": "hello"})
    discovery = registry.load_by_name(["echo"])
    output = s03.handle_defer_execute(registry, "echo", {"value": "hello"})

    assert "Call ToolSearch first" in denied
    assert discovery.matches[0].schema["input_schema"]["required"] == ["value"]
    assert registry.get_loaded_names() == ("echo",)
    assert output == "HELLO"


def test_tool_search_does_not_turn_immediate_tools_into_deferred_tools() -> None:
    s03 = load_s03()
    registry = s03.ToolRegistry()
    registry.register(
        "read_file",
        deferred_schema("read_file", "Read a file."),
        lambda value: value,
        defer=False,
    )

    discovery = registry.load_by_name(["read_file"])
    output = s03.handle_defer_execute(registry, "read_file", {"value": "notes.md"})

    assert discovery.matches == ()
    assert discovery.missing == ("read_file",)
    assert "is immediate; call it directly" in output
