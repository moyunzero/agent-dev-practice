"""第 2 课：自然语言 → SQL Agent（create_agent + 三工具）。"""

from __future__ import annotations

import os
import sys

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from db_config import DB_PATH
from sql_tools import SQL_TOOLS

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")

SYSTEM = """你是 SQLite 数据分析助手。必须使用工具查库，禁止编造数字。
流程：先 sql_db_list_tables，再 sql_db_schema 看相关表，最后 sql_db_query 执行 SELECT。
调用 sql_db_schema 时，table_names 必须是字符串，例如 "sales" 或 "products,sales"，不要传 JSON 数组。
调用 sql_db_list_tables 时不要传参数。
列名必须与 schema / 样例行完全一致（例如销量列是 qty，不是 quantity）。
若 sql_db_query 返回 SQL 错误：必须根据错误和 schema 改写 SQL，再次调用 sql_db_query，直到成功或确认无法查询；不要只口头说「应该改成某某」却不重试。
需要商品名称时 JOIN products。只读：禁止 INSERT/UPDATE/DELETE/DROP。
用中文简要回答，并引用查询到的数字。"""


def _text(content) -> str:
    return content if isinstance(content, str) else str(content)


def print_react_trace(messages: list) -> None:
    step = 0
    for msg in messages:
        if isinstance(msg, AIMessage):
            if msg.tool_calls:
                for call in msg.tool_calls:
                    step += 1
                    print(f"Thought {step}: 调用 {call['name']}")
                    print(f"Action {step}: {call['name']}({call['args']})")
                text = _text(msg.content).strip() if msg.content else ""
                if text:
                    print(f"(中间文本) {text}")
        elif isinstance(msg, ToolMessage):
            preview = _text(msg.content)
            if len(preview) > 400:
                preview = preview[:400] + "..."
            print(f"Observation: {preview}")

    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not msg.tool_calls:
            text = _text(msg.content).strip() if msg.content else ""
            if text:
                print(f"Answer: {text}")
            break


def main() -> None:
    if not DB_PATH.exists():
        print(f"请先运行: uv run python step01_init_and_peek.py\n缺少 {DB_PATH}")
        sys.exit(1)

    question = sys.argv[1] if len(sys.argv) > 1 else "哪个商品总销量最高？卖了多少件？"

    agent = create_agent(
        model=f"ollama:{OLLAMA_MODEL}",
        tools=SQL_TOOLS,
        system_prompt=SYSTEM,
    )

    print(f"DB: {DB_PATH}")
    print(f"Q: {question}\n")
    print("--- ReAct 轨迹 ---")
    result = agent.invoke({"messages": [{"role": "user", "content": question}]})
    print_react_trace(result["messages"])


if __name__ == "__main__":
    main()
