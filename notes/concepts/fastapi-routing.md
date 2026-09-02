# FastAPI 路由

- ID：`concept-fastapi-routing`
- 首次出现：Week 01 Day 01
- 相关日记：`notes/week01/day01-fastapi.md`

## 一句话

路由 =「HTTP 方法 + URL 路径」绑定到一个 Python 函数；函数返回值通常变成 JSON 响应。

## 为什么重要

Agent / RAG 服务对外都是 API。路由设计清楚，后面加检索、工具调用、监控才有挂载点。

## 最小例子

```python
@app.get("/items/{item_id}")   # path
def read_item(item_id: int): ...

@app.get("/search")            # query: ?q=&limit=
def search(q: str, limit: int = 5): ...

@app.post("/chat")             # body: JSON → Pydantic
def chat(body: ChatRequest): ...
```

## 常见误解

- 以为「写了函数就会自动变成接口」——必须用 `@app.get/post` 挂上。
- 分不清 path 和 query——看参数是在路径里还是在 `?` 后面。

## 链接

- 相关概念：`openai-compatible-providers`
- 外部来源：https://fastapi.tiangolo.com/tutorial/path-params/
