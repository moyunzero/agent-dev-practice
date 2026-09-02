# 掌握 MD 与 PDF 的加载和文本分块策略：RAG 的第一步

Day2 你理解了 LangChain 的 **Indexes**——外部知识要先检索，再塞进 Prompt。但检索的对象不能是「整本 PDF」或「整篇 wiki」，必须先变成很多**小块**。这就是 RAG Part 1：**加载（Loader）+ 分割（Splitter）**。

本文从零讲清：不同格式文档怎么加载、`Document` 长什么样、两种常用**分块策略**怎么选、`chunk_size` / `chunk_overlap` 如何影响结果。全文自包含，代码可直接复制运行。**这一步不调用大模型**，却是后面向量检索的地基。

## 你将会得到什么

1. 说清 `Document`、`Loader`、`Splitter`、`chunk` 各自职责  
2. 跑通 MD（`TextLoader`）与 PDF（`PyPDFLoader`）的加载  
3. 对比两种分块策略：`RecursiveCharacterTextSplitter` 与 `MarkdownHeaderTextSplitter`  
4. 能根据文档类型选型，并解释 `chunk_size` / `chunk_overlap` / `separators`  
5. 理解 PDF 常见 pipeline：先按页 load，再页内 split  

---

## 零基础名词表

### RAG 在本篇的位置

```text
磁盘上的文件 (.md / .pdf)
        │  Loader（加载）              ◀── 本篇上半段
        ▼
List[Document]   page_content + metadata
        │  Splitter（切分）            ◀── 本篇下半段
        ▼
List[Document]（多个 chunk，块更小）
        │  Embedding + 向量库          ◀── Day4
        ▼
检索 Top-K → 塞进 Prompt → 模型回答
```

### Document 是什么

LangChain 里，**Document** 是装载文本的标准容器：

| 字段 | 存什么 | 例子 |
|------|--------|------|
| `page_content` | 正文（字符串） | `# FastAPI 入门\n\nFastAPI 是…` |
| `metadata` | 来源信息（字典） | `{'source': 'data/sample.md'}` |

**chunk** 不是新类型——切分后每一块**通常仍是 Document**，只是 `page_content` 更短。

### Loader 与 Splitter

| 组件 | 干什么 | 本篇用到的类 |
|------|--------|--------------|
| **Loader** | 从磁盘读文件 → 产出 `Document` 列表 | `TextLoader`（MD/TXT）、`PyPDFLoader`（PDF） |
| **Splitter** | 把过长的 Document 按规则切成多个 chunk | `RecursiveCharacterTextSplitter`、`MarkdownHeaderTextSplitter` |

**顺序永远是 Loader 先、Splitter 后。** 加载阶段通常还没有 chunk。

---

## 格式不同，加载原理不同

| 格式 | 磁盘上是什么 | Loader | 通常几个 Document |
|------|-------------|--------|-------------------|
| **MD / TXT** | UTF-8 纯文本 | `TextLoader` | **1 文件 = 1 个** |
| **PDF（有文字层）** | 二进制，内容按页组织 | `PyPDFLoader` | **1 页 = 1 个** |

Markdown 里的 `#`、`##` 在 Loader 阶段**只是普通字符**，不会自动变成 metadata 里的 `h1` / `h2`——那是 Splitter 的事。

---

## 两种分块策略（上游 Day3 核心）

| 策略 | 类名 | 按什么切 | 适合 |
|------|------|---------|------|
| **递归字符切分** | `RecursiveCharacterTextSplitter` | 长度上限 + 分隔符降级（`\n\n` → `\n` → `。` → 空格 → 硬切） | 纯文本、日志、结构乱的 MD、PDF 页内文字 |
| **Markdown 标题切分** | `MarkdownHeaderTextSplitter` | `#` / `##` 等标题边界 | 有清晰章节的手册、API 文档、笔记 |

**选型口诀：**

```text
MD 有清晰 ## 章节  →  MarkdownHeader（一块 ≈ 一节，metadata 带 h1/h2）
结构乱 / PDF 页内  →  RecursiveCharacter（调 chunk_size / overlap）
一节仍然太长      →  先 Header 切，再 Recursive（二级策略，知道即可）
```

### RecursiveCharacter 的三个参数

| 参数 | 含义 |
|------|------|
| `chunk_size` | 单块**上限**（字符数，不是精确长度） |
| `chunk_overlap` | 相邻块**故意重叠**的字符数，防句子被拦腰截断 |
| `separators` | 分隔符优先级；块仍太长则**递归**尝试下一级 |

「递归」的含义：对切出来仍超长的子块，用下一级分隔符再切，直到只能硬切。

---

## 环境准备（从零开始）

```bash
uv init rag-load-split-day3 && cd rag-load-split-day3
uv add langchain langchain-community langchain-text-splitters pypdf fpdf2
mkdir -p data
```

确认安装：

```bash
uv run python -c "from langchain_text_splitters import RecursiveCharacterTextSplitter; print('ok')"
```

---

## 准备示例文件

### `data/sample.md`

```markdown
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
```

### 生成 2 页 `data/sample.pdf`

保存为 `prepare_sample_pdf.py`：

```python
from pathlib import Path

from fpdf import FPDF

out = Path("data/sample.pdf")
out.parent.mkdir(parents=True, exist_ok=True)

pdf = FPDF()
pdf.set_font("Helvetica", size=12)

pdf.add_page()
pdf.multi_cell(
    0,
    8,
    "Page 1 - FastAPI is a Python web framework for building APIs. "
    "It uses type hints and auto-generates OpenAPI docs. "
    "PyPDFLoader usually returns one Document per page.",
)

pdf.add_page()
pdf.multi_cell(
    0,
    8,
    "Page 2 - RAG loads documents, splits them into chunks, embeds chunks, "
    "retrieves relevant chunks, and injects them into the prompt.",
)

pdf.output(str(out))
print(f"已写入 {out}")
```

```bash
uv run python prepare_sample_pdf.py
```

---

## 第 1 步：先看清 Document（加载 ≠ 分块）

保存为 `step01_document_anatomy.py`：

```python
from pathlib import Path

from langchain_community.document_loaders import TextLoader

MD = Path("data/sample.md")


def main() -> None:
    docs = TextLoader(str(MD), encoding="utf-8").load()
    doc = docs[0]
    print(f"Document 个数: {len(docs)}")
    print(f"metadata: {doc.metadata}")
    print(f"page_content 长度: {len(doc.page_content)} 字符")
    print(f"正文前 120 字:\n{doc.page_content[:120]}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python step01_document_anatomy.py
```

期望：`1 个 Document`，`metadata` 只有 `source`，全文约 **542 字符**。  
此时 `# FastAPI 入门笔记` 和 `## 路由` 都在 **`page_content` 字符串里**，不是 metadata。

---

## 第 2 步：MD 加载 + RecursiveCharacter 分块

保存为 `demo_load_split.py`：

```python
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

DATA = Path("data/sample.md")


def main() -> None:
    docs = TextLoader(str(DATA), encoding="utf-8").load()
    print(f"加载完成：{len(docs)} 个 Document")
    print(f"metadata: {docs[0].metadata}")
    print(f"全文长度: {len(docs[0].page_content)} 字符\n")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=200,
        chunk_overlap=40,
        separators=["\n\n", "\n", "。", " ", ""],
    )
    chunks = splitter.split_documents(docs)

    print(f"切分后：{len(chunks)} 个 chunk\n")
    for i, chunk in enumerate(chunks, start=1):
        preview = chunk.page_content.replace("\n", " ")[:80]
        print(f"[chunk {i}] len={len(chunk.page_content)} | {preview}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_load_split.py
```

典型输出：`chunk_size=200` → **4 个 chunk**。改成 `400` 再跑 → 约 **2 个 chunk**。

---

## 第 3 步：对比两种 MD 分块策略

保存为 `demo_chunk_strategies.py`：

```python
from pathlib import Path

from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

MD = Path("data/sample.md")


def main() -> None:
    text = TextLoader(str(MD), encoding="utf-8").load()[0].page_content

    chunks_a = RecursiveCharacterTextSplitter(
        chunk_size=200, chunk_overlap=40, separators=["\n\n", "\n", "。", " ", ""]
    ).split_text(text)
    print(f"策略 A · RecursiveCharacter：{len(chunks_a)} 块")

    chunks_b = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "h1"), ("##", "h2")]
    ).split_text(text)
    print(f"策略 B · MarkdownHeader：{len(chunks_b)} 块\n")

    for i, chunk in enumerate(chunks_b, start=1):
        preview = chunk.page_content.replace("\n", " ")[:60]
        print(f"[B-{i}] meta={chunk.metadata} | {preview}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_chunk_strategies.py
```

典型输出：

| 策略 | 块数 | 特点 |
|------|------|------|
| A · RecursiveCharacter | **4** | 按长度切，不管有几个 `##` |
| B · MarkdownHeader | **6** | 按章节切，metadata 带 `h1` / `h2` |

策略 B 的 `meta={'h2': '路由'}` 在 RAG 里很有用：检索结果能标注「来自哪一节」，注入 Prompt 时可追溯出处。

---

## 第 4 步：PDF 加载 + 页内再切

保存为 `demo_load_pdf.py`：

```python
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

PDF = Path("data/sample.pdf")


def main() -> None:
    docs = PyPDFLoader(str(PDF)).load()
    print(f"加载完成：{len(docs)} 个 Document（通常每页一个）")
    print(f"第 1 页 metadata: {docs[0].metadata}\n")

    splitter = RecursiveCharacterTextSplitter(chunk_size=120, chunk_overlap=20)
    chunks = splitter.split_documents(docs)
    print(f"切分后：{len(chunks)} 个 chunk\n")
    for i, chunk in enumerate(chunks, start=1):
        page = chunk.metadata.get("page", "?")
        print(f"[chunk {i}] page={page} | {chunk.page_content[:80]}...")


if __name__ == "__main__":
    main()
```

```bash
uv run python demo_load_pdf.py
```

期望：2 页 PDF → **2 个 Document** 加载；`chunk_size=120` 较小 → 页内再切，总共 **多个 chunk**，每个仍带 `page` metadata。

完整 pipeline：

```text
sample.pdf
  → PyPDFLoader.load()                         → 2 个 Document（metadata.page）
  → RecursiveCharacterTextSplitter.split_documents()  → N 个 chunk
```

---

## 关系图：Loader 与 Splitter 分工

```text
  sample.md                          sample.pdf
       │                                   │
       ▼                                   ▼
  TextLoader                         PyPDFLoader
  1 文件 → 1 Document                1 页 → 1 Document
       │                                   │
       ├──────────────┬────────────────────┤
       ▼              ▼                    ▼
 MarkdownHeader   RecursiveCharacter   RecursiveCharacter
 （有 ## 的 MD）   （通用）              （PDF 页内）
       │              │                    │
       ▼              ▼                    ▼
  chunk[] 带 h1/h2   chunk[] 按长度      chunk[] 带 page
```

---

## 踩过的坑

**1）Loader 阶段就把 `##` 当成 metadata 里的 `h2`**

`TextLoader` 加载后，`## 路由` 只是 `page_content` 里的普通字符；`metadata` 只有 `source`。  
只有 **`MarkdownHeaderTextSplitter` 切分之后**，才会出现 `metadata={'h2': '路由'}`。

**2）把 `chunk_overlap` 当成「chunk 最大值」**

限制单块长度的是 **`chunk_size`**；`overlap` 只管相邻块**重复**多少字（最多重叠 `chunk_overlap` 个字符）。

**3）以为 PDF 一定是图片，所以一页一个 Document**

PDF 有**文字层**时，`PyPDFLoader` 能直接抽文本；「一页一个 Document」是因为 **PDF 格式按页组织**，不是因为 PDF = 图片。  
**扫描版** PDF（页内是图片）读出来几乎是空字符串，需要 OCR（MinerU / Docling 等，后续再学）。

**4）终端 `langchain-community` DeprecationWarning**

社区包在迁移中，学习阶段可忽略；生产环境关注官方迁移指南即可。

---

## 取舍与未做之事

本篇覆盖上游 Day3：**MD/PDF 加载 + 两种分块策略 + 参数调优**。

未涉及：Embedding、向量库、检索、生成（Day4–6）。  
复杂 PDF（表格、图片混排）的 Unstructured / MinerU / Docling 解析——Week2 再深入。  
Token 级切分、语义切分——知道存在即可，Day4 结合 embedding 窗口再选。

---

## 小结

- **Loader** 解决「不同格式怎么读出文本」：MD/TXT 用 `TextLoader`，PDF 用 `PyPDFLoader`（按页）  
- **Splitter** 解决「长文怎么切成检索用小块」：结构 MD 用 `MarkdownHeader`，通用场景用 `RecursiveCharacter`  
- **`chunk_size`** 控制块大小；**`chunk_overlap`** 控制块间重叠；PDF 常见「先 load 再 split」  
- 加载 + 分割不调用大模型，但 chunk 切得是否合理，决定 Day4 检索质量的上限  

下一步 Day4：给 chunk 做 **Embedding**，存进本地向量库（FAISS / Chroma）。

---

*系列笔记 · Agent 工程跟练 · Week 1 Day 3*
