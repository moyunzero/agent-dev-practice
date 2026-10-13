"""对抗测试：检查延迟工具签名、参数边界和模型契约的副本隔离。"""

from __future__ import annotations

import copy
import importlib.util
import inspect
import itertools
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_s03():
    """导入离线教学模块，但不运行命令行入口。"""
    module_name = "s03_deferred_schema_adversarial_module"
    spec = importlib.util.spec_from_file_location(
        module_name,
        ROOT / "s03_deferred_loading" / "code.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_deferred_signatures_match_schema_contract():
    """攻击万能参数吞参、额外参数、必填项变可选及无声明默认值被擅自补值。"""
    s03 = load_s03()
    registry = s03.build_registry()
    names = registry.get_deferred_names()
    assert names
    assert set(names) == set(s03.DEFERRED_TOOL_SCHEMAS)

    for tool_name in names:
        schema = registry.load_by_name([tool_name]).matches[0].schema
        rules = schema["input_schema"]["properties"]
        required = set(schema["input_schema"].get("required", []))
        handler = registry.get_handler(tool_name)
        assert handler is not None, tool_name
        parameters = inspect.signature(handler).parameters
        assert set(parameters) == set(rules), tool_name
        assert required <= set(rules), tool_name

        for name, parameter in parameters.items():
            label = f"{tool_name}.{name}"
            assert parameter.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.KEYWORD_ONLY,
            ), label
            if name in required:
                assert parameter.default is inspect.Parameter.empty, label
                continue

            expected = rules[name].get("default")
            # 卡片明确保留此既有例外，不扩大到其他无默认值的参数。
            if (tool_name, name) == ("computer_use", "text"):
                expected = ""
            assert parameter.default == expected, label
            assert type(parameter.default) is type(expected), label


def test_repaired_handlers_keep_parameter_boundaries():
    """攻击部分可选参数组合、零值、非首项枚举以及缺参和多参被静默接受。"""
    s03 = load_s03()
    cases = {
        "image_gen": (
            {"prompt": "示例"},
            {"size": "1792x1024", "style": "vivid", "seed": 0},
        ),
        "image_edit": (
            {"image_path": "input.png", "instruction": "添加夕阳"},
            {"size": "1792x1024"},
        ),
        "lsp": (
            {"operation": "hover", "file_path": "example.py"},
            {"line": 0, "character": 0},
        ),
    }

    for tool_name, (required, optional) in cases.items():
        registry = s03.build_registry()
        s03.handle_tool_search(registry, tool_names=[tool_name])
        assert tool_name in registry.get_loaded_names()

        for count in range(len(optional) + 1):
            for keys in itertools.combinations(optional, count):
                params = {**required, **{key: optional[key] for key in keys}}
                output = s03.handle_defer_execute(registry, tool_name, params)
                assert output.startswith("[MOCK]"), (tool_name, params, output)

        for missing in required:
            params = {key: value for key, value in required.items() if key != missing}
            output = s03.handle_defer_execute(registry, tool_name, params)
            assert output.startswith(f"Error executing {tool_name}:"), output
            assert missing in output, output

        output = s03.handle_defer_execute(
            registry, tool_name, {**required, "undeclared_parameter": 1}
        )
        assert output.startswith(f"Error executing {tool_name}:"), output
        assert "undeclared_parameter" in output, output

        # 这里只验证原有异常边界，不引入本章未承诺的完整类型校验。
        for params in (None, [1], "invalid", 1, {1: "invalid"}):
            output = s03.handle_defer_execute(registry, tool_name, params)
            assert output.startswith(f"Error executing {tool_name}:"), output


def test_schema_copies_cannot_rewrite_registered_contract():
    """攻击源定义、加载结果和序列化结果的嵌套修改污染后续搜索与加载。"""
    s03 = load_s03()
    registry = s03.build_registry()

    def corrupt(schema):
        """修改嵌套容器，以识别只复制顶层字典的错误实现。"""
        schema["input_schema"]["properties"]["injected"] = {"type": "string"}
        schema["input_schema"].setdefault("required", []).append("injected")

    for tool_name in registry.get_deferred_names():
        source = s03.DEFERRED_TOOL_SCHEMAS[tool_name]
        expected = copy.deepcopy(source["input_schema"])
        corrupt(source)

        loaded = registry.load_by_name([tool_name]).matches[0]
        assert loaded.schema["input_schema"] == expected, tool_name

        payload = loaded.to_payload()
        corrupt(payload["schema"])
        assert loaded.schema["input_schema"] == expected, tool_name

        corrupt(loaded.schema)
        searched = registry.search([tool_name], top_k=1).matches[0]
        assert searched.name == tool_name
        assert searched.cache_hit
        assert searched.schema["input_schema"] == expected, tool_name

        corrupt(searched.schema)
        reloaded = registry.load_by_name([tool_name]).matches[0]
        assert reloaded.cache_hit
        assert reloaded.schema["input_schema"] == expected, tool_name
