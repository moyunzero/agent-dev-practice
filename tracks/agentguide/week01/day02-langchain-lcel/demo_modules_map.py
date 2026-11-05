"""Day2：理解 Indexes / Agents（概念示意，不求一次做完 RAG/Agent）。"""

print(
    """
【Indexes 在解决什么】
  模型参数里装不下你的私有文档。Indexes 相关能力负责：
  文档加载 → 切分 → 向量化 → 存进向量库 → 按问题检索相关片段
  检索到的片段再塞进 Prompt，模型才能「依据你的资料」回答。
  → 这就是后面 Naive RAG（Day3–6）要动手的整条链。

【Agents 在解决什么】
  普通 Chain / LCEL：流水线是你事先写死的（prompt→model→parser）。
  Agent：模型当「调度员」，自己决定要不要调用工具、调用哪个
  （搜网页、查数据库、算数……），再根据工具结果继续想。
  → 这就是后面 Week3 Tool Calling / Agent 要动手的内容。

【和今天 LCEL 的关系】
  Models + Prompts + Chains(LCEL) = 固定流水线（你已在练）
  Memory = 给流水线带上对话历史
  Indexes = 给流水线接入外部知识（RAG）
  Agents = 让模型在流水线之外还能「选工具」
"""
)
