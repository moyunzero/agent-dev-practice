"""第 2 课：工具说明书从哪里来 — docstring + 类型注解 → schema。"""

from __future__ import annotations

from langchain.tools import tool


@tool
def get_word_length(word: str) -> int:
    """Return character count of a word."""
    return len(word)


@tool
def multiply(a: int, b: int) -> int:
    """Multiply two integers."""
    return a * b


def show_tool_card(t) -> None:
    """把 LangChain 给 LLM 看的「工具名片」打印出来。"""
    print(f"=== 工具名: {t.name} ===")
    print(f"说明(description): {t.description}")
    print("参数 schema（JSON）:")
    # args_schema 是 Pydantic 模型；model_json_schema 是模型真正「看到」的结构摘要
    schema = t.args_schema.model_json_schema()
    props = schema.get("properties", {})
    required = schema.get("required", [])
    for name, info in props.items():
        tip = "【必填】" if name in required else "【可选】"
        typ = info.get("type", "?")
        print(f"  - {name}: 类型={typ} {tip}")
    print()


def main() -> None:
    print("人写的：普通 Python 函数 + docstring + 参数类型")
    print("LangChain @tool 做的：变成 LLM 能读的「工具名片」(schema)\n")

    for t in (get_word_length, multiply):
        show_tool_card(t)

    print("--- 亲手验证：函数本身还能当普通函数用 ---")
    print("get_word_length.invoke({'word': 'agent'}) ->", get_word_length.invoke({"word": "agent"}))
    print("multiply.invoke({'a': 5, 'b': 3}) ->", multiply.invoke({"a": 5, "b": 3}))
    print()
    print("链式调用（人脑版）:")
    print("  1) 先 length = get_word_length('agent')  → 5")
    print("  2) 再 multiply(5, 3)                     → 15")
    print("Agent 版：模型读完两张名片，自己决定第 1、2 步顺序（见第 1 课 demo）。")


if __name__ == "__main__":
    main()
