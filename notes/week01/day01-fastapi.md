# 用 FastAPI 搭一个能同时打 Ollama 和 OpenRouter 的最小 API

如果你几乎没做过后端，也想开始做「能调大模型的小服务」，可以从这篇跟一遍。读完并照做后，你会在自己的电脑上跑起一个网址：别人（或你自己的前端）用 HTTP 请求它，它再去问本地或云端的大模型，把答案用 JSON 返回来。

本文**不要求**你事先读过 FastAPI / Ollama / OpenRouter 的其它文章。下面会先补齐会用到的名词，再给完整可复制代码。

## 你将会得到什么

做成之后，你的电脑上会有一个小服务，大致长这样：

```text
你的终端 / 浏览器
        │  HTTP 请求（例如 POST /chat）
        ▼
   FastAPI 小服务（本机 8000 端口）
        │
        ├─ provider=ollama      → 本机 Ollama 里的模型
        └─ provider=openrouter  → 网上的 OpenRouter（可用免费模型）
```

成功标准（全部满足才算跟完）：

1. 浏览器打开 `http://127.0.0.1:8000/docs` 能看到接口文档  
2. `GET /` 返回 Hello World  
3. `POST /chat` 用本地模型能聊一句  
4. （可选但推荐）填好 Key 后，同一接口改用 OpenRouter 也能聊  

---

## 零基础名词表（读代码前先看）

### API 是什么

**API**可以先理解成「给程序用的菜单」：写明有哪些菜（接口）、怎么点（请求怎么发）、端上来是什么（返回什么）。

网页是给人看的；API 常常是给程序看的。你的前端、脚本、别的服务，都通过 API 跟后端说话。

### HTTP：双方约定好的「打电话方式」

浏览器或 `curl` 访问一个网址时，用的就是 **HTTP**。你需要先记住四个很常见的词：

| 词 | 人话 |
|----|------|
| **URL / 路径** | 要找哪扇门，例如 `/chat`、`/items/3` |
| **方法（Method）** | 对这扇门做什么。本文用到 `GET`（取数据）和 `POST`（提交数据） |
| **请求体（Body）** | 主要出现在 `POST`：把 JSON 数据放进信封寄过去 |
| **状态码** | 服务器回你的「结果标签」：`200` 成功，`400` 你少带了东西，`422` 格式/取值不合法，`502` 上游（比如模型服务）出错 |

### JSON：程序之间最常见的「表格文字」

JSON 长这样：

```json
{"message": "Hello, World"}
```

花括号里是键值对。Python 里的 `dict`（字典）和它几乎一一对应，所以 FastAPI 里 `return {"message": "..."}` 就会变成上面这种 JSON。

### FastAPI 和 Uvicorn 分别干什么

- **FastAPI**：你用来「定义菜单」的 Python 框架——哪个路径、什么方法、参数长什么样、返回什么。  
- **Uvicorn**：真正在端口上「听电话」的服务器进程。没有它，FastAPI 只是一份说明书，外面打不进来。

常见启动方式：

```bash
uv run uvicorn main:app --reload --port 8000
```

含义拆开：

- `main:app`：去 `main.py` 里找名为 `app` 的那个应用对象  
- `--reload`：你改代码后自动重启（适合学习）  
- `--port 8000`：监听本机 8000 端口，所以网址是 `http://127.0.0.1:8000`

### 大模型、Ollama、OpenRouter

- **大模型（LLM）**：根据你输入的文字，生成回复的模型（ChatGPT 那一类能力）。  
- **Ollama**：把模型跑在**你自己电脑**上的工具。优点是数据不出门、不烧云端额度；缺点是要下载模型、吃本地内存/显存。  
- **OpenRouter**：一个**网上的模型路由/超市**。你申请一个 Key，就可以按它的 API 去调用很多家模型；其中也有标注免费的模型额度。  

两者都能提供「看起来很像 OpenAI」的聊天接口，所以我们用同一套 Python 客户端，只换地址和 Key。

### SDK、OpenAI 兼容是什么意思

- **SDK**：别人写好的调用库。你不用自己拼每一条 HTTP 细节。本文用的是官方风格的 `openai` Python 包。  
- **OpenAI 兼容**：很多本地/云端服务故意做成「和 OpenAI 聊天接口差不多」的形状。于是你可以：

```text
换 base_url（服务地址）+ 换 api_key 策略
→ 业务代码几乎不用改
```

### `.env`：把秘密和配置放在代码外面

`.env` 是一个本地文本文件，用来放：

- 模型名  
- 服务地址  
- **API Key（千万别发到公开地方）**

程序启动时读进去。这样你分享代码时，可以只给别人一份「空的示例」，不泄露自己的 Key。

### `uv` 是什么（可替换）

`uv` 是一个很快的 Python 包/项目管理工具。本文用它创建项目、装依赖。如果你更熟 `pip` + `venv`，等价思路是：建虚拟环境 → `pip install fastapi uvicorn openai pydantic-settings python-dotenv`。

### `curl` 是什么

`curl` 是终端里发 HTTP 请求的小工具，用来验证 API，不必先写前端。

- `-s`：少打印进度  
- `-S`：出错时仍显示错误（强烈建议学习时带上）  
- `-H`：加请求头  
- `-d`：加请求体  

没有 `curl` 也没关系：服务启动后打开 `/docs`，用网页按钮试即可。

---

## 要解决什么问题

「脚本里直接调模型」适合五分钟 Demo。但只要你想：

- 给网页/小程序调用  
- 统一校验参数  
- 今天用本地模型、明天用云端免费模型  

就更适合先做一个小 API。本文交付的就是这个最小骨架。

---

## 环境准备（从零开始）

### 1. 安装 Python 3.12+

终端执行：

```bash
python3 --version
```

若版本过旧，先从 [python.org](https://www.python.org/downloads/) 安装。

### 2. 安装 uv（推荐）

macOS / Linux 可参考 [uv 安装说明](https://docs.astral.sh/uv/getting-started/installation/)。装好后：

```bash
uv --version
```

### 3. 安装并启动 Ollama，拉取一个小模型

1. 安装：[ollama.com](https://ollama.com)  
2. 确保 Ollama 在运行（安装后一般会常驻）  
3. 拉取模型（体积小、适合练手）：

```bash
ollama pull qwen3:0.6b
ollama list
```

能在列表里看到模型名即可。

### 4. （推荐）准备 OpenRouter Key

1. 打开 [openrouter.ai/keys](https://openrouter.ai/keys) 注册并创建 Key  
2. 先复制保存好，下一步写入 `.env`  
3. 模型名可先用 `openrouter/free`（由 OpenRouter 路由到免费模型池；若不可用，可在其模型列表里换成带 `:free` 的具体模型名）

### 5. 创建项目并安装依赖

```bash
uv init fastapi-ollama-openrouter
cd fastapi-ollama-openrouter
uv add fastapi "uvicorn[standard]" openai pydantic-settings python-dotenv
```

### 6. 创建 `.env`

在项目目录新建文件 `.env`（注意文件名以点开头）：

```bash
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:0.6b
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=sk-or-v1-把这里换成你的密钥
OPENROUTER_MODEL=openrouter/free
```

如果暂时只用本地 Ollama，Key 可以先空着；那时 `provider=openrouter` 会返回明确的 400 提示。

---

## 完整代码

把下面内容完整保存为项目里的 `main.py`（若 `uv init` 已生成过同名文件，直接覆盖即可）：

```python
"""FastAPI + Ollama / OpenRouter（OpenAI 兼容协议）最小示例。"""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """从环境变量 / .env 读取配置，避免把密钥写死在代码里。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:0.6b"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/free"


settings = Settings()
app = FastAPI(title="FastAPI Ollama OpenRouter", version="0.1.0")


class ChatRequest(BaseModel):
    """客户端发来的 JSON 必须符合这个形状，否则 FastAPI 直接返回 422。"""

    prompt: str = Field(min_length=1, examples=["用一句话介绍 FastAPI"])
    provider: Literal["ollama", "openrouter"] = "ollama"
    temperature: float = Field(default=0.2, ge=0, le=2)


class ChatResponse(BaseModel):
    provider: str
    model: str
    content: str


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello, World"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/items/{item_id}")
def read_item(item_id: int) -> dict[str, int | str]:
    """路径参数示例：访问 /items/3 时，item_id 自动等于 3。"""
    return {"item_id": item_id, "name": f"item-{item_id}"}


@app.get("/search")
def search(q: str, limit: int = 5) -> dict[str, str | int]:
    """查询参数示例：访问 /search?q=fastapi&limit=2。"""
    return {"q": q, "limit": limit}


def _client(provider: Literal["ollama", "openrouter"]) -> tuple[OpenAI, str]:
    """按 provider 构造 OpenAI 兼容客户端，并返回要使用的模型名。"""
    if provider == "ollama":
        # openai 包创建客户端时通常要求传 api_key；
        # Ollama 本地默认不校验它，所以任意非空字符串都能占位。
        return (
            OpenAI(base_url=settings.ollama_base_url, api_key="ollama"),
            settings.ollama_model,
        )

    if not settings.openrouter_api_key:
        raise HTTPException(
            status_code=400,
            detail="缺少 OPENROUTER_API_KEY，请写入 .env",
        )
    return (
        OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        ),
        settings.openrouter_model,
    )


@app.post("/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    client, model = _client(body.provider)
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": body.prompt}],
            temperature=body.temperature,
        )
    except Exception as exc:
        # 模型服务挂了、网络不通、模型名写错等，统一变成 502，方便排查
        raise HTTPException(
            status_code=502,
            detail=f"{body.provider} 调用失败: {exc}",
        ) from exc

    content = completion.choices[0].message.content or ""
    return ChatResponse(provider=body.provider, model=model, content=content)
```

---

## 这段代码在干什么（对照着读）

### 1. `Settings`：读配置

`BaseSettings` 会尝试从环境变量和 `.env` 里找同名配置（例如字段 `openrouter_api_key` 对应 `OPENROUTER_API_KEY`）。这样密钥不用写进 `main.py`。

### 2. `app = FastAPI(...)`：创建应用

后面所有 `@app.get` / `@app.post` 都挂在这个对象上。Uvicorn 启动时加载的就是它。

### 3. 路由：哪扇门由谁开

```python
@app.get("/")
def root(): ...
```

读作：当有人用 **GET** 访问 `/` 时，调用 `root`，把它的返回值变成 JSON。

三种参数，建议第一天就分清：

| 类型 | 长什么样 | 本文例子 |
|------|----------|----------|
| Path（路径参数） | 嵌在路径中 | `/items/3` → `item_id=3` |
| Query（查询参数） | `?` 后面 | `/search?q=fastapi&limit=2` |
| Body（请求体） | JSON | `POST /chat` 里的 `{"prompt":"..."}` |

FastAPI 主要看**函数参数怎么声明**：路径里有同名变量 → 当 path；否则常见是 query；若参数类型是 Pydantic 模型且方法是 POST，则常从 JSON body 解析。

### 4. Pydantic：先检查，再干活

`ChatRequest` 规定：

- `prompt` 至少 1 个字符  
- `provider` 只能是 `ollama` 或 `openrouter`  
- `temperature` 必须在 0～2  

如果你传 `"temperature": 9`，框架直接 **422**，函数体里的模型调用根本不会执行。这比「调到一半才报错」友好。

### 5. `_client`：同一套 SDK，两套后端

| 后端 | base_url | api_key |
|------|----------|---------|
| Ollama | `http://localhost:11434/v1` | 任意非空占位即可 |
| OpenRouter | `https://openrouter.ai/api/v1` | 必须是真实 Key |

真正聊天只有一句核心：

```python
client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": body.prompt}],
    temperature=body.temperature,
)
```

`messages` 就是对话列表；这里演示最简单的「只有一条用户消息」。

---

## 启动与验证

在项目目录执行：

```bash
uv run uvicorn main:app --reload --port 8000
```

看到类似 `Uvicorn running on http://127.0.0.1:8000` 就成功了。**先保持这个终端不要关**，另开一个终端做下面的请求。

### 用浏览器（最省事）

打开：`http://127.0.0.1:8000/docs`  
这是 FastAPI 自动生成的交互文档：点开接口 → Try it out → Execute。

### 用 curl（训练手感）

```bash
curl -sS http://127.0.0.1:8000/
# 期望：{"message":"Hello, World"}

curl -sS http://127.0.0.1:8000/health
# 期望：{"status":"ok"}

curl -sS http://127.0.0.1:8000/items/3
# 期望：{"item_id":3,"name":"item-3"}

curl -sS 'http://127.0.0.1:8000/search?q=fastapi&limit=2'
# 期望：{"q":"fastapi","limit":2}

curl -sS http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"只回复：OK","provider":"ollama","temperature":0}'
# 期望：content 字段里有模型回复（小模型可能不止回一个 OK，但应有文本）
```

测 OpenRouter（需 `.env` 里已有 Key）：

```bash
curl -sS http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"用一句话介绍 FastAPI","provider":"openrouter"}'
```

故意传错，观察校验：

```bash
curl -sS http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"x","provider":"ollama","temperature":9}'
# 期望：HTTP 422，提示 temperature 不能大于 2
```

---

## 踩过的坑（零基础特别容易中招）

**1）服务没启动，却以为「接口坏了」。**  
`curl -s` 在连不上时可能几乎不显示内容。请用 `curl -sS`，或先看启动终端是否还在跑，或先访问 `/health`。

**2）改了 `.env` 却没生效。**  
配置多半在进程启动时读入。改完 Key / 模型名后，确认 Uvicorn 已重启（`--reload` 有时对 `.env` 不如对 `.py` 敏感，不行就手动停掉再启动）。

**3）Ollama 没模型或没在跑。**  
`/chat` 会变成 502，详情里通常能看到连接或模型相关错误。先 `ollama list`，再确认 Ollama 应用/服务已打开。

**4）把真实 Key 发到公开地方。**  
Key 只放 `.env`，不要贴进截图、聊天和公开仓库。若泄露，去 OpenRouter 控制台作废并重建。

**5）以为「本地就不需要 api_key 这个参数」。**  
对 Ollama 而言 key 常常无鉴权意义，但 `openai` 客户端创建时仍可能要求你传一个非空字符串。占位是为了满足 SDK，不是因为本地更安全。

---

## 取舍与未做之事

为了让零基础读者一篇读完就能跑通，本文刻意不做：

- 登录鉴权、限流  
- `Depends` 依赖注入  
- 高并发异步细节  
- Docker 部署  

这些都很重要，但会显著增加第一篇的认知负担。path / query / body 都写了，是因为「会处理请求」是搭 API 的最低完整集；双后端是为了后面做 RAG / Agent 时少改架构。

---

## 小结

你现在应当具备这三块直觉：

1. **API = 对外的门**：用 FastAPI 定义门，用 Uvicorn 看守端口  
2. **先校验再调模型**：Pydantic 让坏请求停在 422  
3. **换地址就能换模型供应商**：OpenAI 兼容协议让 Ollama 和 OpenRouter 共用同一套调用代码  

下一步，通常会把「一次 `/chat`」升级成可组合的模型链式调用（例如 LangChain 的 LCEL），但入口仍然可以是今天这个 FastAPI 服务。

---

*系列笔记 · Agent 工程跟练 · Week 1 Day 1*
