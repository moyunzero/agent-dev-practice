# Day27 — vLLM-Metal 启动备忘（路径 A-Metal）

## 安装（一次性，较大）

```bash
# 确认 arm64 + 3.12
~/.local/bin/python3.12 -c 'import platform; print(platform.machine(), platform.python_version())'

curl -fsSL https://raw.githubusercontent.com/vllm-project/vllm-metal/main/install.sh | bash
```

默认环境：`~/.venv-vllm-metal`

## 起服务

```bash
source ~/.venv-vllm-metal/bin/activate
# 先用小模型；首次会下载权重
vllm serve mlx-community/Qwen2.5-0.5B-Instruct-4bit --port 8027
```

若 `vllm serve` 无模型参数写法有变，以 `vllm serve --help` 为准。

## 验收 curl（另开终端）

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
```

看到 `choices[0].message.content` 有文本即过关。
