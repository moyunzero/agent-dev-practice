#!/usr/bin/env bash
# Day29 Lesson 2 — 带 LangSmith 跑研究助手（需先 cp .env.example .env 并填 KEY）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DAY21="$ROOT/../../week03/day21-research-assistant"

if [[ ! -f "$ROOT/.env" ]]; then
  echo "缺少 $ROOT/.env — 请先: cp .env.example .env 并填入 LANGCHAIN_API_KEY"
  exit 1
fi

set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

# 只拒 .env.example 里的占位符；真实 LangSmith key 也是 lsv2_pt_ 开头，不能用通配符
if [[ -z "${LANGCHAIN_API_KEY:-}" || "${LANGCHAIN_API_KEY}" == "lsv2_pt_xxxxxxxx" ]]; then
  echo "请在 .env 里填入真实的 LANGCHAIN_API_KEY（勿留 example 里的 lsv2_pt_xxxxxxxx）"
  exit 1
fi

QUESTION="${1:-Nebula Router 的内部协议版本和桶数分别是什么？请依据知识库回答。}"

cd "$DAY21"
uv sync
echo "LangSmith project: ${LANGCHAIN_PROJECT:-default}"
echo "Q: $QUESTION"
echo "---"
uv run python demo_research_agent.py "$QUESTION"
echo "---"
echo "打开 https://smith.langchain.com → Projects → ${LANGCHAIN_PROJECT:-default} 查看最新 trace"
