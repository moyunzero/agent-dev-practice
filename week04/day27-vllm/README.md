# Week 4 / Day 27 — vLLM-Metal 部署与吞吐

> **状态**：`available`
> 对外文章：[用 vLLM-Metal 部署开源模型并测吞吐：墙钟、req/s、token/s 怎么读](../../notes/week04/day27-vllm.md)

## 前置

- Apple Silicon（arm64）+ Python 3.12  
- 已安装 vLLM-Metal 到 `~/.venv-vllm-metal`（见对外文章安装节）

## 验收命令

**终端 A — 起服务：**

```bash
source ~/.venv-vllm-metal/bin/activate
vllm serve mlx-community/Qwen2.5-0.5B-Instruct-4bit --port 8027
```

等到 `Application startup complete`。

**终端 B — curl + 吞吐：**

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

**期望**：`/v1/models` 列出模型；chat 有 `choices[0].message.content`；吞吐脚本并发 wall 明显短于串行。

## 收工清理

```bash
# 终端 A：Ctrl+C 停 serve
rm -rf __pycache__ .venv
# ~/.venv-vllm-metal 按需保留或删除
```
