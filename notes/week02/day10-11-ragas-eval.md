# 用 RAGAs 评估 RAG：Faithfulness、Answer Relevancy 与优化前后对比

Day8 改了问句，Day9 加了 Hybrid 检索和 Rerank——你觉得「应该更准了」。但**感觉不能当证据**：同一问句下，Naive 和 Hybrid 到底谁 Top-1 更对？答案有没有瞎编？改了一版检索，分数涨没涨？

**RAG 评估** 要回答的就是这些。本文用开源框架 **RAGAs**，在本地 **Ollama** 上当 Judge，量化 **Faithfulness（忠实度）** 和 **Answer Relevancy（答案相关性）**；并对比 **仅向量** vs **Hybrid+Rerank** 两档流水线。全文自包含，按步骤复制即可复现。

## 你将会得到什么

1. 说清 Faithfulness / Answer Relevancy 各量在问什么、低分先查哪一环  
2. 用 RAGAs + Ollama 给固定样本自动打分  
3. 对比 Naive 与 Hybrid+Rerank 的评测结果，并会看 **检索日志**（不能只看一个均值）  
4. 搭一条可复用评估流水线：`collect_rows` 收卷 → `run_ragas_eval` 打分  
5. 知道 Judge JSON 失败、小评测集误导等常见坑  

---

## 零基础名词表

### RAG 流水线（评估插在哪？）

```text
用户问句
  → 检索 contexts（Top-K 段）
  → 拼 Prompt
  → LLM 生成 answer
```

评估通常读三样东西：**question**、**contexts**、**answer**。  
`ground_truth`（标准答案）可选，有则部分指标更稳；本篇最小集也会写上，方便以后扩展。

### Faithfulness（忠实度）

**答案里的陈述，能不能被检索到的 context 支撑？**

| 分数 | 含义 |
|------|------|
| 高 | 关键事实在 context 里找得到依据 |
| 低 | 答案「编」了 context 没有的内容 → 先查检索是否捞错/漏，再查生成是否幻觉 |

### Answer Relevancy（答案相关性）

**答案有没有正面回应用户问句？**

| 分数 | 含义 |
|------|------|
| 高 | 紧扣问题 |
| 低 | 跑题、泛泛而谈 → 多为生成 / Prompt / 问句理解问题 |

两个指标可以 **一高一低**：答案看起来在答问句，但 context 撑不住（Faithfulness 低）。

### Context Precision / Recall（扩展直觉）

| 指标 | 量在问什么 |
|------|------------|
| **Context Precision** | 捞上来的段里，有多少真是相关的？（检索精度） |
| **Context Recall** | 该出现的要点，检索漏了多少？（检索召回） |

本篇主跑 Faithfulness + Answer Relevancy；Precision/Recall 理解即可，RAGAs 也支持，后续可加。

### RAGAs 是什么？

**RAG Assessment** — 用 LLM 当「裁判（Judge）」给 RAG 输出打分。  
输入：`question`、`contexts`（**列表**，每段一条）、`answer`；输出：各指标 0～1，**越高越好**。

Judge **不是**答题那只 LLM：要独立、常选 instruction 与 JSON 能力更强的模型，且 `temperature=0` 求可复现。

---

## 问题从哪来：凭感觉改 RAG 不够

典型翻车：

| 现象 | 可能根因 |
|------|----------|
| 答案像人话但不对 | 检索 Top-1 错了，模型仍「编」步骤 |
| 检索对了，答案跑题 | Prompt / 生成环节 |
| 优化后 aggregate 分数反降 | 评测集太小、chunk 切分合并、Judge 波动 |

所以流程应是：**先看 Top-1 检索 → 再看 answer → 再用 RAGAs 量化**；不能只看一个均值。

---

## 环境准备

**需要**：Python 3.12+、[uv](https://docs.astral.sh/uv/)、[Ollama](https://ollama.com/) 已启动。

```bash
mkdir rag-eval-demo && cd rag-eval-demo
uv init --python 3.12
uv add "ragas>=0.4.0,<0.5.0" datasets langchain-ollama langchain-huggingface langchain-openai \
  "langchain-community>=0.3.0,<0.4" langchain-chroma langchain-text-splitters \
  chromadb rank-bm25 sentence-transformers
```

拉模型（Judge 与生成；可按本机已有模型替换）：

```bash
ollama pull qwen2.5-coder:7b   # Judge，JSON 能力较好
ollama pull qwen2:7b           # RAG 生成（可换）
```

首次运行会从 HuggingFace 下载 Embedding（`all-MiniLM-L6-v2`，384 维，与 Chroma 默认兼容）。国内网络不稳时可设镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
```

> **依赖说明**：`ragas` 0.2.x 与 0.4.x API 差异大，请锁 **`ragas>=0.4.0,<0.5.0`**；`langchain-community` 建议 **`>=0.3.0,<0.4`**（0.4+ 与 ragas 0.4.3 import 可能冲突）。`langchain-ollama` 0.1+ 支持 `format="json"`。

---

## 第 0 步：样例知识库

保存 `data/sample.md`：

```markdown
# FastAPI 与 RAG 运维笔记

## 分块参数

- **chunk_size**：每块的最大字符数。太小则上下文碎片化；太大则可能超过模型窗口。
- **chunk_overlap**：相邻块之间的重叠字符数。有助于避免一句话被拦腰截断而丢失语义。

## 错误码 ERR_CHUNK_42

当向量索引未重建却更新了源文档时，系统可能返回错误码 **ERR_CHUNK_42**。
处理步骤：停止写入 → 清空旧 collection → 重新 embed 全量 chunk → 再开放查询。
```

教学用库很小（切分后约 3 块），**足够演示流程**；生产对比请用更大、更干净的评测集。

---

## 第 1 步：指标直觉（不写 RAGAs，先建立判断力）

下面 4 个场景是「人工标注的参考答案」；跑脚本前可先自己想哪项会低。

**场景 ②（检索错 → 无 context 依据）** 与 Day9 呼应：问 `ERR_CHUNK_42`，context 却是分块参数，答案却在讲错误码处理 → **Faithfulness 低**。

注意：答案未必是模型「瞎编」——也可能是 **预训练常识** 里恰好有类似处理步骤。RAGAs 的 Faithfulness **只认 context 里有没有依据**，不认模型「本来就知道」。口语叫幻觉，指标上统一判 **unsupported by context**。

保存 `step01_metrics_intuition.py`（节选）：

```python
SCENARIOS = [
    {
        "name": "② 检索错了 → 幻觉",
        "question": "ERR_CHUNK_42 怎么处理？",
        "contexts": ["chunk_size 建议 200～500；chunk_overlap 建议 50～100。"],
        "answer": "ERR_CHUNK_42 表示索引不一致。应停止写入、清空 collection、重新 embed。",
        "faithfulness": "低",
        "answer_relevancy": "中～高",
    },
    # ... ① 理想、③ 答非所问、④ 检索漏要点
]
```

```bash
uv run python step01_metrics_intuition.py
```

**要点**：Faithfulness 低 → 先检索后生成；Answer Relevancy 低 → 先看生成/Prompt。

---

## 第 2 步：RAGAs 最小跑通

### 评测集长什么样？

| 列 | 类型 | 说明 |
|----|------|------|
| `question` | 字符串 | 用户问句 |
| `contexts` | **字符串列表** | 检索到的多段，每段一条 |
| `answer` | 字符串 | 模型最终输出 |
| `ground_truth` | 字符串（可选） | 人工标准答案；**Faithfulness / Answer Relevancy 不读此列**（预留 Context Recall 等） |

### Judge 配置（Ollama 本地）

保存 `eval_common.py`：

```python
import os
from datasets import Dataset
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_ollama import ChatOllama
from ragas import evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import AnswerRelevancy, Faithfulness
from ragas.run_config import RunConfig

os.environ.setdefault("OPENAI_API_KEY", "local-not-used")  # 避免 RAGAs 误走 OpenAI

JUDGE_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def build_judge():
    llm = LangchainLLMWrapper(
        ChatOllama(
            model=JUDGE_MODEL,
            temperature=0,
            num_predict=4096,
            timeout=600,
            format="json",
        )
    )
    embeddings = LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(model_name=EMBED_MODEL)
    )
    return llm, embeddings


def run_ragas_eval(rows: list[dict]) -> dict:
    dataset = Dataset.from_list(rows)
    llm, embeddings = build_judge()
    # ragas 0.4.x：构造时注入 llm/embeddings（勿 faithfulness.llm = llm 事后赋值）
    faithfulness = Faithfulness(llm=llm)
    answer_relevancy = AnswerRelevancy(llm=llm, embeddings=embeddings)

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy],
        llm=llm,
        embeddings=embeddings,
        run_config=RunConfig(timeout=600, max_workers=1),
    )
    df = result.to_pandas()
    return {
        "faithfulness": float(df["faithfulness"].mean(skipna=True)),
        "answer_relevancy": float(df["answer_relevancy"].mean(skipna=True)),
        "df": df,
    }
```

`demo_ragas_baseline.py` 把第 1 课 3 个场景填进 `SAMPLES`，直接 `run_ragas_eval(SAMPLES)`。  
3 条样本 + Judge 约 **5～10 分钟**（Faithfulness 更慢）。

**期望现象**（Judge 正常时）：

| 样本 | faithfulness | answer_relevancy |
|------|-------------|------------------|
| ① 理想 | 高 | 高 |
| ② 检索错 | **低** | 中～低 |
| ③ 跑题 | 低 | **低** |

---

## 第 3 步：两档 RAG + 对比评估

### 两档检索（映射 Day4 / Day9）

| 模式 | 行为 |
|------|------|
| `naive` | 仅 Chroma 向量 `similarity_search(k=TOP_K)` |
| `hybrid_rerank` | BM25 + 向量 → RRF 融合 → CrossEncoder 精排 → Top-K |

`rag_store.py` 里 `run_pipeline(mode, question, ...)` 返回：

```python
{"question": ..., "contexts": [...], "answer": "..."}
```

生成 Prompt 与 Naive RAG 相同（只改检索），对比实验才公平。

### 单问句快速对比（推荐先跑）

```bash
uv run python demo_eval_pipeline.py --mode hybrid_rerank \
  --question "ERR_CHUNK_42 怎么处理？"

uv run python demo_eval_pipeline.py --mode naive \
  --question "ERR_CHUNK_42 怎么处理？"
```

**实测 Top-1 对比**：

| 模式 | Top-1 |
|------|-------|
| hybrid_rerank | **错误码段**（`## 错误码 ERR_CHUNK_42`） |
| naive | **分块参数段**（`## 分块参数`） |

答案可能「都像在答错误码」，但 **context 不同** —— 这就是必须看检索日志的原因。

### 完整 RAGAs 对比（慢）

```bash
OLLAMA_MODEL=qwen2.5-coder:7b uv run python demo_ragas_compare.py
# 或
OLLAMA_MODEL=qwen2.5-coder:7b uv run python demo_eval_pipeline.py --compare
```

**可能看到的反直觉结果**：aggregate 均值上 naive 的 faithfulness 反而 ≥ hybrid。原因包括：

1. **库只有 3 块 + TOP_K=2**，两档 context 高度重叠  
2. **chunk 切分** 把多节合并，Top-1 不同但第二段仍混入噪声  
3. **样本仅 3 条**，一条波动拉垮均值  
4. **Faithfulness=1.0** 只表示「答案能被当前 context 支撑」，不表示「检索最优」

工程结论：**ERR_CHUNK_42 问句上 hybrid 的 Top-1 纠正** 仍成立；aggregate 分数在小库上不可过度解读。

---

## 第 4 步：可复用流水线

```text
data/eval_set.json   ← 考卷（改问句不改 Python）
       ↓
collect_rows(mode)   ← 跑 RAG，收集 question/contexts/answer
       ↓
run_ragas_eval(rows) ← Judge 打分（可选，慢）
```

保存 `data/eval_set.json`：

```json
[
  {
    "question": "ERR_CHUNK_42 怎么处理？",
    "ground_truth": "停止写入，清空 collection，重新 embed 全量 chunk。"
  },
  {
    "question": "chunk_overlap 是干什么的？",
    "ground_truth": "相邻分块之间的重叠字符数，避免切断句子。"
  }
]
```

> **关于 `ground_truth`**：上表虽含标准答案，但本节只跑 **Faithfulness / Answer Relevancy**，RAGAs **不会用** `ground_truth` 参与打分。该列预留后续 **Context Recall**、`answer_correctness` 等；勿误以为「传了就会算对」。

CLI 速查：

| 命令 | 作用 | 耗时 |
|------|------|------|
| `--mode naive --question "..."` | 单档单问，只看 Top-1 + answer | 快 |
| `--mode hybrid_rerank --score` | 整份 eval_set + RAGAs | 慢 |
| `--compare` | 两档 + RAGAs | 很慢 |

**流水线一句话**：先 `collect_rows` 收卷，再 `run_ragas_eval` 打分；题在 JSON 里；默认 `--mode` 只收卷不打分，为了快。

---

## 踩过的坑

### 1）Judge 吐 prompt 模板 → faithfulness = nan

**现象**：`OutputParserException(Invalid json output: Your task is to judge the faithfulness...)`  

**原因**：`qwen2:7b` 等模型常把 RAGAs 的 JSON schema 说明原样输出，而非填好 `{"statements":[...]}`。  

**处理**：换 Judge（如 `qwen2.5-coder:7b`）、`format="json"`、`num_predict` 提到 **4096**（长 answer 拆 statements 时 JSON 易被截断）、`RunConfig(timeout=600)`。

### 2）答案像人话，但 Top-1 错了

Naive 在 `ERR_CHUNK_42` 上 Top-1 是分块参数，模型仍可能编出「停止写入、清空 collection」—— 若 context 里没有这些字，Faithfulness 应低；若模型只复述 context 里有的，Faithfulness 仍可能不低。**不能只看 answer 像不像。**

### 3）检索对了，生成说「资料未提及」

问 `chunk_size 建议范围`，Top-1 已是分块参数段，answer 却说「资料未提及」并补常识 —— **检索 OK，生成未守 Prompt**。Faithfulness / Relevancy 都可能被拉低。说明评估要 **检索、生成分层看**。

### 4）小库 + 合并 chunk 误导 aggregate 分

Top-1 标签应按 **chunk 内最先出现的主题** 打，不能「含 ERR 就标错误码」—— 同一块可能既有 `chunk_overlap` 又有 `ERR_CHUNK_42`。

### 5）对比实验必须控制变量

固定：同一批问句、同一 Judge、同一生成 Prompt。  
只改：检索链（naive vs hybrid_rerank）。  
否则分数差异无法归因。

---

## 本文边界

| 做了 | 没做 |
|------|------|
| Faithfulness、Answer Relevancy | Context Precision/Recall 完整实验 |
| RAGAs + Ollama Judge | TruLens、DeepEval 全家桶 |
| Naive vs Hybrid+Rerank 对比 | Query Transform 单独对比 |
| 可复用 `eval_pipeline` + JSON 评测集 | 大规模标注集、线上 A/B |

---

## 小结

1. **Faithfulness** 看 answer 是否被 context 支撑；**Answer Relevancy** 看是否答问句。  
2. **RAGAs** 用独立 Judge LLM 打分；`contexts` 是列表；本地优先 Ollama + 强 JSON 模型。  
3. 对比优化前后：**固定问句与 Prompt，只改检索**；先看 Top-1，再看 aggregate 分。  
4. **流水线** = `collect_rows` 收卷 → `run_ragas_eval` 打分；日常调试可只跑 `--mode` 不打分。  
5. 小评测集 + 弱 Judge 会出 nan 或反直觉均值 —— 这是评估课的一部分，不是 RAG 白做了。

下一篇可接 **Milvus 生产向量库（Day12）** 或把 Hybrid 检索集成进 Week1 的 `POST /ask` 并定期跑 `eval_set.json`。
