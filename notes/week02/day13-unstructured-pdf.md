# 用 Unstructured 解析含表格与图片的复杂 PDF：补上 RAG 的「文档入口」

简单 PDF 用 PyPDF 按页抽文本就够了。一旦页面里出现**表格、多栏、嵌入图、扫描件**，同一套 Loader 往往会把列挤成一行、把图里的字丢掉——后面的分块、Embedding、检索全在「坏原料」上运转。

**Unstructured** 把 PDF 拆成带类型的 **Element**（Title / Table / NarrativeText / Image…），再用 `hi_res` 做版面检测：表格更容易收成 `Table`，嵌入图可能收成 `Image`。本文从空目录复现：**对比 PyPDF 局限 → `partition_pdf` → fast vs hi_res → 表格与带图样例 → 转成 LangChain Document → 复用分块器**，并说明何时考虑 **MinerU** / OCR。全文自包含。

## 你将会得到什么

1. 说清「复杂 PDF」复杂在哪，以及 PyPDF 与 Unstructured 各适合什么场景  
2. 用 `partition_pdf` 看 Element 类型；对比 `fast` / `hi_res` 何时出现 `Table`、`Image`  
3. 分清：**嵌入图**（有文字层）vs **整页扫描**（常需 OCR）  
4. 把 Element 转成 `Document`，接入分块；知道下游 embed / 向量库不用改——换的是 **Loader 质量**  
5. 会选型：通用解析用 Unstructured；学术/复杂版面/公式更强可看 MinerU  
6. 避开：fast 无 Table/Image、忽略 `text_as_html`、误以为检出 Image 就等于图中文字可检索  

---

## 零基础名词表

> 若你刚接触 RAG 文档加载，建议先读完本节再动手。每个词按「是什么 → 在本文干什么 → 怎么区分」展开。

### RAG 里「文档加载」占哪一步？

```text
原始 PDF
    ↓  Loader / partition     ← 本文重点
List[Document] 或 Element[]
    ↓  Text Splitter
chunks
    ↓  Embedding → 向量库 → Top-K → Prompt → LLM
```

**Loader 回答**：怎么从文件里抽出可检索的文本？  
**Splitter 回答**：整篇太长，按什么规则切块？  

本文只升级 **Loader**；Splitter / Embed / 向量库可与常见 Naive RAG 流程相同。

### 简单 PDF vs 复杂 PDF

| | 简单 PDF | 复杂 PDF |
|--|----------|----------|
| **是什么** | 有清晰文字层、单栏、少表格 | 表格 / 多栏 / 嵌入图 / 扫描图 / 图文混排 |
| **在本文** | 用 `simple_two_page.pdf` 对照 | `complex_sample.pdf`（表格）+ `with_image_sample.pdf`（嵌入图） |
| **怎么区分** | PyPDF 输出可读、顺序正常 | PyPDF 常把表格挤成一行；图中文字进不了检索 |

「复杂」不只是页数多，而是 **版面结构** 让「按页抽文本流」不够用。

### PyPDFLoader：按页抽纯文本

| 层 | 说明 |
|----|------|
| **是什么** | LangChain 对 pypdf 的封装：通常 **1 页 → 1 个 Document** |
| **在本文干什么** | 作为基线：展示复杂 PDF 上表格如何变乱 |
| **怎么区分** | 快、依赖少；**不做版面分析**，不产出 Table 类型 |

适合：纯文本、结构简单、有可选中文字层的 PDF。  
不适合：要保留表格行列关系、多栏阅读顺序、扫描件 OCR。

### Unstructured 与 `partition_pdf`

| 层 | 说明 |
|----|------|
| **是什么** | 开源非结构化文档解析库；`partition_pdf` 专门处理 PDF |
| **在本文干什么** | 把 PDF 拆成 **Element 列表**，并尝试识别表格 |
| **怎么区分** | 不是「再写一个按页 Loader」，而是 **元素级解析** |

相关工具怎么选：

| 工具 | 定位 | 本文 |
|------|------|------|
| **Unstructured** | 通用非结构化解析，和 LangChain 好接 | **主线实操**（表格 + 嵌入图） |
| **MinerU** | 学术 PDF、公式、复杂版面，偏重型 | **会选型**：版面/公式很难时再上；本文不装全套 GPU |
| **Docling** | IBM 开源文档理解 | 了解即可 |

一句话：日常 RAG 文档入口优先 Unstructured；论文/公式/极复杂版面再评估 MinerU。

### Element：带类型的文档块

| 层 | 说明 |
|----|------|
| **是什么** | Unstructured 的解析单元，有类型名（`Title`、`Table`、`NarrativeText`…）和文本内容 |
| **在本文干什么** | `partition_pdf` 的返回值；再转成 LangChain `Document` |
| **怎么区分** | PyPDF 的 Document 通常只有「这一页的字」；Element 额外回答「**这块是什么**」 |

常见类型直觉：

| 类型 | 含义 | RAG 用途 |
|------|------|----------|
| **Title** | 标题类短文本 | 可加权或作章节边界 |
| **NarrativeText** | 正文段落 | 常规 chunk |
| **Table** | 表格区域 | 可单独建索引 / 过滤 |
| **Text** | 未细分的文本 | 兜底 |

### `strategy`：`fast` vs `hi_res`

| | `fast` | `hi_res` |
|--|--------|----------|
| **是什么** | 有文字层时走 pdfminer 抽文本 + 规则分类 | 版面检测模型识别区域与类型 |
| **在本文干什么** | 第 2 课快速看 Element；常 **没有 Table** | 第 3 课配合表格结构推断 |
| **怎么区分** | 快，表格易碎成 Title/NarrativeText | 慢，更可能产出完整 `Table` |

**忘记选 hi_res 会怎样**：表格仍在，但类型标签没有，后面按 `category=="Table"` 过滤会得到空列表。

### `infer_table_structure` 与 `text_as_html`

| 层 | 说明 |
|----|------|
| **是什么** | `infer_table_structure=True`：解析时尝试还原表格；成功时 `Table.metadata` 常带 **`text_as_html`**（HTML `<table>`） |
| **在本文干什么** | 先保证出现 `Table`；进阶再把 HTML 转成带 `|` 的可读文本再 embed |
| **怎么区分** | **类型标签**（`category=Table`）≠ **行列结构已进 Embedding**。只用 `str(el)` 往往是平铺字符串；真正保留列关系要读 `text_as_html` |

### Image 元素与「图里的字」

| 层 | 说明 |
|----|------|
| **是什么** | Unstructured 在版面检测后可能标出的 **Image**（或 Figure）类元素：表示这里有一块图 |
| **在本文干什么** | `with_image_sample.pdf` + `hi_res`：类型计数里出现 `Image: 1`；`fast` 往往只有 Title/NarrativeText |
| **怎么区分** | **检出 Image ≠ 图里的字已进文本**。图是像素；若要把图中文字送进 RAG，还要 OCR 或人工写 caption |

### 嵌入图 PDF vs 整页扫描 PDF

| | 嵌入图（本文样例） | 整页扫描件 |
|--|--------------------|------------|
| 结构 | 有可选中**文字层** + 另贴一张图 | 整页往往就是一张图，**没有文字层** |
| 解析 | `hi_res` 可能产出 Image；正文仍可抽取 | 不 OCR 时几乎抽不到字 |
| 下一步 | 决定：只存 caption、对图 OCR、或多模态 embed | 必须 OCR（Unstructured OCR 路径）或换 MinerU 等方案 |

### 扫描件与 OCR

| 层 | 说明 |
|----|------|
| **是什么** | 从图片里**识别文字**的技术（如 Tesseract；Unstructured 可走 `ocr_only` 等策略） |
| **在本文干什么** | 解释：扫描件 / 图内文字为何检索不到；主线样例有文字层，不强制跑通 OCR 生产链 |
| **怎么区分** | `hi_res` 是版面分析，**不等于**自动把每张图 OCR 成全文 |

### LangChain `Document` 与转换桥

| 层 | 说明 |
|----|------|
| **是什么** | 统一载体：`page_content`（文本）+ `metadata`（字典） |
| **在本文干什么** | Splitter / VectorStore 吃的是 `List[Document]`，不是裸 Element |
| **怎么区分** | Element → Document 是 **必做桥接**；缺这一步，Day3 的 Splitter 接不上 |

推荐在 metadata 里写入 `category=type(el).__name__`，便于过滤、加权、单独建索引。

### TextSplitter（复习一句）

`RecursiveCharacterTextSplitter` 按长度上限 + 分隔符优先级切块。  
**它只能切已有文本，修不好坏解析**——表格乱了，再调 `chunk_size` 也只是把乱字切得更碎。

---

## 环境准备

- Python 3.12+  
- 包管理器任选（下文用 `uv`）  
- 首次 `hi_res` 会从 HuggingFace 下载版面模型（体积大、耗时长），需网络；可设镜像：`export HF_ENDPOINT=https://hf-mirror.com`  
- `unstructured[pdf]` 依赖重（推理栈、poppler 等）；macOS/Linux 教学路径最顺。Windows 上布局模型相关依赖更容易踩坑——先跑通 `strategy="fast"` / `"auto"`，再按需开 `hi_res`  
- 保底：`strategy="auto"` 会在「可抽文字」时走 fast，需要表格结构推断时倾向 hi_res（见官方策略解析逻辑）

```bash
mkdir complex-pdf-demo && cd complex-pdf-demo
uv init --python 3.12
uv add "langchain-community>=0.3.0,<0.4" langchain-core langchain-text-splitters \
  pypdf reportlab "unstructured[pdf]>=0.16.0"
mkdir -p data scripts
```

---

## 第 0 步：生成对照样例 PDF

保存 `scripts/generate_sample_pdfs.py`（生成含表格的 `data/complex_sample.pdf`）：

```python
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DATA = Path(__file__).resolve().parents[1] / "data"


def write_complex_sample() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    out = DATA / "complex_sample.pdf"
    styles = getSampleStyleSheet()
    table_data = [
        ["Code", "Meaning", "Fix"],
        ["ERR_CHUNK_42", "Index out of sync with source docs",
         "Stop writes → rebuild collection → re-embed all"],
        ["ERR_EMBED_DIM", "Vector dim != schema dim",
         "Check embedding model vs Milvus dim"],
    ]
    t = Table(table_data, colWidths=[90, 140, 220])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]
        )
    )
    story = [
        Paragraph("RAG Ops Manual · Error Code Reference", styles["Title"]),
        Spacer(1, 12),
        Paragraph(
            "When the vector index is stale after source doc updates, "
            "queries may return inconsistent results.",
            styles["Normal"],
        ),
        Spacer(1, 12),
        t,
        Spacer(1, 12),
        Paragraph(
            "Rule: stop writes → clear or rebuild index → "
            "re-embed all chunks → reopen search.",
            styles["Normal"],
        ),
    ]
    SimpleDocTemplate(str(out), pagesize=letter).build(story)
    print("wrote", out)


if __name__ == "__main__":
    write_complex_sample()
```

```bash
uv run python scripts/generate_sample_pdfs.py
```

会得到：`complex_sample.pdf`（表格）、`with_image_sample.pdf`（嵌入 PNG）、以及简单对照 PDF。仓库里需有 `data/diagram_placeholder.png`（可用极小占位图）。

---

## 带图样例：`fast` 不见 Image，`hi_res` 能检出

```python
from collections import Counter
from unstructured.partition.pdf import partition_pdf

pdf = "data/with_image_sample.pdf"
for strategy in ("fast", "hi_res"):
    els = partition_pdf(filename=pdf, strategy=strategy)
    print(strategy, dict(Counter(type(e).__name__ for e in els)))
```

期望（量级因版本略有差异）：

- `fast`：多为 `Title` / `NarrativeText`，**常常没有 Image**  
- `hi_res`：类型里出现 **`Image: 1`**，同时仍有正文 NarrativeText  

记住：出现 `Image` 只说明「这里有一块图」；**图里写的字**要进 RAG，还得 OCR 或手写说明文字。整页扫描、没有文字层时，更要走 OCR / 评估 MinerU。

---

## 第一步：看清 PyPDF 的局限

```python
from pathlib import Path
from langchain_community.document_loaders import PyPDFLoader

path = Path("data/complex_sample.pdf")
docs = PyPDFLoader(str(path)).load()
print("pages:", len(docs))
print(docs[0].page_content[:200].replace("\n", " "))
```

**期望现象**：标题、正文、表头、单元格往往挤在同一页字符串里，列对齐消失。  
这就是后面检索「ERR_CHUNK_42 怎么处理？」时，错误码与 Fix 列可能被切散或语义变弱的根源。

---

## 第二步：`partition_pdf` 看 Element

```python
from pathlib import Path
from unstructured.partition.pdf import partition_pdf

elements = partition_pdf(
    filename=str(Path("data/complex_sample.pdf")),
    strategy="fast",
)
print("count:", len(elements))
for el in elements:
    print(type(el).__name__, "|", str(el)[:80].replace("\n", " "))
```

**期望**：得到多个 Element（不是「整页一条」）；常见 `Title` / `NarrativeText`。  
在 **`fast`** 下，**经常没有 `Table`**——表格被拆成标题和正文碎片。这正常，下一步用 `hi_res`。

---

## 第三步：`fast` vs `hi_res`，找出 Table

```python
from pathlib import Path
from unstructured.partition.pdf import partition_pdf

pdf = str(Path("data/complex_sample.pdf"))

for strategy, infer in [("fast", False), ("hi_res", True)]:
    elements = partition_pdf(
        filename=pdf,
        strategy=strategy,
        infer_table_structure=infer,
    )
    kinds = {}
    for el in elements:
        name = type(el).__name__
        kinds[name] = kinds.get(name, 0) + 1
    tables = [el for el in elements if type(el).__name__ == "Table"]
    print(strategy, "kinds=", kinds, "tables=", len(tables))
    if tables:
        print("  table preview:", str(tables[0])[:200])
```

**典型对照（教学样例）**：

| strategy | element 数（约） | 有 Table？ |
|----------|------------------|-----------|
| `fast` | 8 | 否（表头变 Title，行变 NarrativeText） |
| `hi_res` + `infer_table_structure=True` | 5 | **是**（整张表收成 1 个 Table） |

`hi_res` 首次会加载版面模型，比 `fast` 慢很多，这是精度换时间。

---

## 第四步：接入分块 — Element → Document → Splitter

```python
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from unstructured.partition.pdf import partition_pdf

pdf = Path("data/complex_sample.pdf")
splitter = RecursiveCharacterTextSplitter(
    chunk_size=200,
    chunk_overlap=40,
    separators=["\n\n", "\n", "。", " ", ""],
)


def element_text(el) -> str:
    """优先用表格 HTML，避免只塞平铺 str(el)。"""
    html = getattr(getattr(el, "metadata", None), "text_as_html", None)
    if type(el).__name__ == "Table" and html:
        return html_table_to_pipes(html)  # 见下一节
    return str(el)


def elements_to_documents(elements) -> list[Document]:
    docs = []
    for el in elements:
        meta = {"category": type(el).__name__}
        page = getattr(getattr(el, "metadata", None), "page_number", None)
        if page is not None:
            meta["page"] = page
        docs.append(Document(page_content=element_text(el), metadata=meta))
    return docs


# A. PyPDF 基线
pypdf_chunks = splitter.split_documents(PyPDFLoader(str(pdf)).load())
print("PyPDF chunks:", len(pypdf_chunks))

# B. Unstructured hi_res
elements = partition_pdf(
    filename=str(pdf),
    strategy="hi_res",
    infer_table_structure=True,
)
uns_docs = elements_to_documents(elements)
uns_chunks = splitter.split_documents(uns_docs)
print("Unstructured chunks:", len(uns_chunks))
for c in uns_chunks:
    print(" ", c.metadata.get("category"), "|", c.page_content[:60].replace("\n", " "))

# C. 只保留 Table
table_docs = [d for d in uns_docs if d.metadata["category"] == "Table"]
table_chunks = splitter.split_documents(table_docs)
print("Table-only chunks:", len(table_chunks))
```

**要点**：

1. **桥接**：`elements_to_documents` 把 Element 变成 Splitter 能吃的 `Document`。  
2. **metadata.category**：可过滤「仅 Table」、加权 Title、或分库索引。  
3. **下游不变**：`chunks → Embedding → Chroma / Milvus`；换的是入口质量。  
4. **表格内容**：有 `text_as_html` 时不要只用 `str(el)`（见下一节）。

**小实验**：把 `chunk_size` 从 200 改成 100，块数会变多（例如 PyPDF 3→6、Unstructured 5→7、仅 Table 1→3）。  
这说明 Splitter 只改切分粒度；**不会**把 `fast` 下碎掉的表格自动拼回一张 `Table`。

---

## 进阶：把 HTML 表格转成可读行列再分块

`infer_table_structure=True` 且识别成功时，`Table.metadata.text_as_html` 类似：

```html
<table><tr><td>ERR_CHUNK_42</td><td>Index out of sync...</td><td>Stop writes...</td></tr>...</table>
```

若把平铺 `str(el)` 直接 embed，模型仍难「看出」列关系。更稳妥：转成带分隔符的文本（或 Markdown 表）再写入 `page_content`。

最小实现（标准库，无额外依赖）：

```python
from html.parser import HTMLParser


class _TableToPipes(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []
            self._in_cell = True

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._in_cell:
            self._row.append("".join(self._cell).strip())
            self._in_cell = False
        elif tag == "tr" and self._row:
            self.rows.append(self._row)

    def handle_data(self, data):
        if self._in_cell:
            self._cell.append(data)


def html_table_to_pipes(html: str) -> str:
    p = _TableToPipes()
    p.feed(html)
    lines = [" | ".join(row) for row in p.rows if any(row)]
    return "\n".join(lines)
```

生产里也可用 BeautifulSoup / `html2text` 转 Markdown。**先确认 `text_as_html` 非空**——有的 PDF 只有 `Table` 类型、没有可用 HTML，这时退回 `str(el)` 并人工抽检。

---

## 常见坑

### 1. 用 `fast` 却期望有 `Table`

**现象**：类型统计只有 Title / NarrativeText。  
**原因**：fast 不做可靠版面表格检测。  
**处理**：`strategy="hi_res"` 且 `infer_table_structure=True`。

### 2. 把 Element 直接丢给 Splitter

**现象**：类型错误或无法 `split_documents`。  
**原因**：Splitter 要的是 `List[Document]`。  
**处理**：先 `elements_to_documents`。

### 3. 以为调小 `chunk_size` 能修好表格

**现象**：块更多，但内容仍乱。  
**原因**：解析质量差时，切分只是切乱字。  
**处理**：先换 Loader / strategy，再调分块参数。

### 4. `hi_res` 很慢或模型下载失败

**现象**：卡住、HF 超时、安装体积巨大。  
**处理**：设 `HF_ENDPOINT` 镜像；教学先 `fast` / `auto`；确认磁盘与内存。Windows 上布局依赖更容易失败，不要一上来就强开完整推理栈。

### 5. 有 `Table` 类型，但仍只用平铺 `str(el)`

**现象**：能按 category 过滤，Embedding 仍难利用列关系。  
**处理**：读取 `metadata.text_as_html`，转成 `|` 分隔或 Markdown 再入库（见上一节）。

### 6. 扫描件（无文字层）仍用默认参数

**现象**：页面是图，`hi_res` 也几乎抽不到表内文字。  
**处理**：改用 `strategy="ocr_only"`（或确保 OCR 依赖如 Tesseract 可用），并配置 `languages`；耗时与资源显著上升。本文样例有文字层，未展开 OCR 生产链。

### 7. 多栏 PDF：阅读顺序仍可能乱

**现象**：左栏底部接到右栏顶部，chunk 语义断裂。  
**原因**：版面检测出区块后，**排序策略不一定等于人类阅读顺序**；多栏是硬问题。  
**处理**：抽检坐标与文本顺序；难例考虑专用版面工具（MinerU / Docling 等）。**不要**假设「只要写 `hi_res_model_name=detectron2` 就一定修好多栏」——模型名/版本随 Unstructured 演进，且多栏后处理往往还要额外规则。

---

## 边界：做了什么 / 故意没做什么

**做了**：复杂 PDF 痛点对照；Unstructured `partition_pdf`；`fast` / `hi_res`；**表格**与 **嵌入图** 样例；Element → Document → Splitter；Unstructured vs MinerU 选型；OCR 与扫描件边界说明。

**没做**：MinerU / Docling 全量 GPU 部署；扫描件 OCR 端到端生产链；多模态「直接 embed 图片」；Unstructured Cloud API；把解析结果写入向量库并跑完整评测（可与常见 embed/向量库流程自行拼接）。

---

## 小结

| 步骤 | 动作 |
|------|------|
| 看清问题 | PyPDF 把表格挤成一行 |
| 元素解析 | `partition_pdf` → Element 列表 |
| 要表格 | `hi_res` + `infer_table_structure=True` |
| 接 RAG | Element → Document（带 category）→ Splitter → embed |

复杂 PDF 的关键不是「换一个更长的 chunk」，而是 **换一个能看懂版面的入口**。Unstructured 补的是 RAG 最前面那一环；后面半链路可以复用你已有的分块与向量库。
