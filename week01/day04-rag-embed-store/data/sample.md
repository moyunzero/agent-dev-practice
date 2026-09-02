# FastAPI 入门笔记

FastAPI 是一个用于构建 API 的 Python Web 框架。它基于类型注解，能自动生成 OpenAPI 文档。

## 路由

使用 `@app.get` 和 `@app.post` 把 URL 绑定到 Python 函数。函数返回的字典会自动变成 JSON。

## 请求校验

Pydantic 模型可以描述请求体的形状。非法字段会在进入业务逻辑之前被拒绝，通常返回 HTTP 422。

## 与 LangChain 的关系

Day1 用 FastAPI 暴露 HTTP 入口；Day2 用 LCEL 组织模型调用；Day3 开始把**文档**加载并切分成 chunk，为 RAG 的 Indexes 模块做准备。

RAG 的典型流程是：加载文档 → 切分 → 向量化 → 检索 → 把检索结果塞进 Prompt → 模型生成答案。

## 分块参数

- **chunk_size**：每块的最大字符数。太小则上下文碎片化；太大则可能超过模型窗口。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 小结

加载与分割本身不调用大模型，但决定了后面检索质量的上限。
