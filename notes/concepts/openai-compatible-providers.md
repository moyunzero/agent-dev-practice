# OpenAI 兼容双后端

- ID：`concept-openai-compatible-providers`
- 首次出现：Week 01 Day 01
- 相关日记：`notes/week01/day01-fastapi.md`

## 一句话

很多本地/云端推理服务都提供「看起来像 OpenAI」的 HTTP API；业务侧用同一套 SDK，只换 `base_url` 和 key 策略。

## 为什么重要

跟练要同时用免费云端（OpenRouter）和本地（Ollama）。兼容层让后面的 LangChain / RAG 少改代码。

## 最小例子

```text
Ollama:     base_url=http://localhost:11434/v1   api_key=任意非空占位
OpenRouter: base_url=https://openrouter.ai/api/v1 api_key=真密钥
```

## 常见误解

- 「本地所以必须特殊 SDK」——不必，Ollama 已提供兼容端点。
- 「api_key 对 Ollama 有安全意义」——本地默认不校验；占位只是为了满足 SDK。

## 链接

- 相关概念：`fastapi-routing`
- 外部来源：https://openrouter.ai/docs 、https://github.com/ollama/ollama/blob/main/docs/openai.md
