# Week 4 / Day 27 — vLLM-Metal 部署与吞吐

> **状态**：`available`  
> **长文教程**（可选）：[用 vLLM-Metal 部署开源模型并测吞吐](../../notes/week04/day27-vllm.md)  
> **补充说明**：[`SERVE.md`](SERVE.md) — serve 参数与排障

## 今日目标

Apple Silicon 上用 vLLM-Metal 起 OpenAI 兼容服务；测串行 vs 并发吞吐（wall / req/s / tok/s）。

## 前置

- **arm64 Mac** + Python 3.12
- 独立 venv：`~/.venv-vllm-metal`（安装见长文或 `SERVE.md`）
- 本目录脚本不通过 `uv sync` 装 vLLM

## 文件说明

| 文件 | 作用 |
|------|------|
| `SERVE.md` | vLLM-Metal 安装、`vllm serve` 参数、curl 示例 |
| `measure_throughput.py` | **主脚本**：串行 8 请求 vs 并发 8 请求；打印 wall / req/s / completion_tok/s |
| `README.md` | 本文件 |

> 无 `pyproject.toml`：吞吐脚本用系统 `python3` 或 vLLM venv 的 Python 运行。

## 推荐顺序

| 步骤 | 做什么 |
|:----:|--------|
| 0 | 按 `SERVE.md` 安装 vLLM-Metal（一次性） |
| 1 | 终端 A：`vllm serve mlx-community/Qwen2.5-0.5B-Instruct-4bit --port 8027` |
| 2 | 等到 `Application startup complete` |
| 3 | 终端 B：`curl /v1/models` 与 chat completion 冒烟 |
| 4 | 终端 B：`python3 measure_throughput.py` |

## 验收命令（汇总）

**终端 A：**

```bash
source ~/.venv-vllm-metal/bin/activate
vllm serve mlx-community/Qwen2.5-0.5B-Instruct-4bit --port 8027
```

**终端 B：**

```bash
curl -s http://127.0.0.1:8027/v1/models | head -c 500
echo

curl -s http://127.0.0.1:8027/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "messages": [{"role": "user", "content": "用一句话介绍 vLLM"}],
    "max_tokens": 64
  }'

python3 measure_throughput.py
```

## 验收标准

- chat 返回 `choices[0].message.content`
- 吞吐脚本：并发 wall 明显短于串行；能解释 req/s、completion_tok/s

## 收工清理

```bash
# 终端 A：Ctrl+C 停 serve
# ~/.venv-vllm-metal 按需保留
```
