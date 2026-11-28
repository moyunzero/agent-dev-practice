# Prompt Assembly：从召回候选到预算内上下文

> *Prompt 不是写死的字符串，也不是把召回结果直接拼进去。Harness 必须先选择，再装箱，最后才组装。*
>
> **Harness 层**：RAG / Context 的 selection → pack 边界。

s12 已经能召回：`query → candidate → score → stable rank → RecallResult`。  
但「召回到」不等于「应该进入 Prompt」。本章做后半条链：门禁、权限、去重、冲突、top-k/预算装箱，再把结果装进系统提示的十类片段。

> 配图：`images/s15-prompt-assembly.svg`

## 你将会得到什么

1. 召回到 ≠ 该进 Prompt；先选再装箱再组装  
2. S12 出分；S15 只适配不重算、不写回长期记忆  
3. Candidate / Policy / Plan 契约；chars ≠ tokens  
4. 三层 authority（本轮 > 工作区 > 默认）≠ 加分权重；≠ required  
5. 选择顺序不可换；同文不同槽不去重；冲突败者不回填  
6. 两层预算 + 两套决策日志；`priority` ≠ `budget_priority`  
7. clear 防泄漏；误区与练习方向；串 s16 Skills  

---

## 零基础名词表

### RecallResult（召回结果）

| 层 | 说明 |
|----|------|
| **是什么** | S12 交出的命中列表：带 scope、score、rank、provenance |
| **在本文干什么** | 作为 S15 的输入原料，不直接等于 Prompt 正文 |
| **怎么区分** | ≠ 最终进系统提示的名单 |

### MemoryContextCandidate（候选卡）

| 层 | 说明 |
|----|------|
| **是什么** | 一条准备参与选择的记忆投影 |
| **在本文干什么** | 携带 text、scope、score、authority、可选 `conflict_key` |
| **怎么区分** | ≠ 已选中；多数候选会被拒绝并留下原因码 |

### conflict_key（事实槽位）

| 层 | 说明 |
|----|------|
| **是什么** | 显式声明「争同一件事」的槽名，如 `preference:automation-language` |
| **在本文干什么** | 同槽不同内容走冲突；同文不同槽不去重 |
| **怎么区分** | 不靠模型读自然语言猜矛盾 |

### PreferenceAuthority（偏好权限层级）

| 层 | 说明 |
|----|------|
| **是什么** | `current_turn` / `workspace_override` / `user_default` 三层 |
| **在本文干什么** | 决定谁赢、谁先装箱；同层才比 score |
| **怎么区分** | ≠ 给分数加权；≠ Harness required 安全规则 |

### MemorySelectionPolicy（选择规矩）

| 层 | 说明 |
|----|------|
| **是什么** | `min_score`、`top_k`、`max_chars`、`max_tokens` |
| **在本文干什么** | 门多紧、筐多大；字符与 token 是两道独立闸 |
| **怎么区分** | ≠ 总系统提示的 `PROMPT_BUDGET_CHARS` |

### 两套决策日志

| 层 | 说明 |
|----|------|
| **是什么** | Memory 层 `MemorySelectionDecision` + 总 Prompt 层 `SegmentDecision` |
| **在本文干什么** | 分别回答「为什么没选这条记忆」与「为什么没放这个片段」 |
| **怎么区分** | 选中了仍可能整段 memory 被总预算 dropped |

### PromptSegment（系统提示片段）

| 层 | 说明 |
|----|------|
| **是什么** | 系统提示的一块积木（base / memory / tools / mode…） |
| **在本文干什么** | `priority` 管展示顺序；`budget_priority` 管抢预算；`required` 不可删 |
| **怎么区分** | required 超预算 → `PromptBudgetError`，不静默删安全规则 |

### estimate_context_tokens（教学粗算）

| 层 | 说明 |
|----|------|
| **是什么** | 离线可复现的教学 token 单位，不是供应商账单 |
| **在本文干什么** | 默认装箱尺子；生产可注入真 tokenizer |
| **怎么区分** | 换尺子可能改变 token 闸门结果，不改变 scope/冲突规则 |

---

## 先装进脑子的总图

```text
RecallResult（S12 已召回）
  → scope 门禁
  → 置信度门禁
  → authority 排队（本轮 > 工作区 > 默认）
  → 精确去重
  → 显式冲突
  → top-k / 字符·token 装箱
  → <recalled_memory> 片段
  → plan_prompt（总预算：先 required，再按 value 抢座位）
  → 最终 system prompt + 两套决策日志
```

S14 管「对话历史太长怎么腾地方」；本章管「记忆候选哪些准进系统提示、十类片段怎么抢总预算」。

---

## S12 与 S15 的职责边界

| | S12 Remote Memory | S15 Prompt Assembly |
|--|-------------------|---------------------|
| 负责 | query、候选、score、稳定排名、scope/provenance | 门禁、authority、去重、冲突、装箱、片段组装 |
| 不负责 | 最终 Prompt 用哪些 hit | 重算检索分；写回长期记忆 |

适配桥只拷贝结构，不偷偷重算分：

```python
def memory_candidates_from_recall(
    result: object,
    *,
    conflict_keys: Mapping[str, str] | None = None,
    authority_by_memory_id: Mapping[str, PreferenceAuthority | str] | None = None,
) -> tuple[MemoryContextCandidate, ...]:
    """Adapt S12 RecallResult: copy scope/score/rank/provenance; do not recompute."""
    # ... 逐条 hit → MemoryContextCandidate ...
    # 默认 authority = user_default
    # 工作区覆盖 / 本轮指令须由可信 harness 经 authority_by_memory_id 注入
```

---

## 核心契约：Candidate / Policy / Plan

```python
@dataclass(frozen=True)
class MemoryContextCandidate:
    memory_id: str
    text: str
    user_scope: str
    score: float                 # 来自 S12，0~1
    source_rank: int             # S12 稳定排名
    provenance: MemoryContextProvenance
    conflict_key: str | None = None
    authority: PreferenceAuthority = PreferenceAuthority.USER_DEFAULT


@dataclass(frozen=True)
class MemorySelectionPolicy:
    min_score: float = 0.35
    top_k: int = 5
    max_chars: int | None = 3_000
    max_tokens: int | None = 800


@dataclass(frozen=True)
class MemoryContextPlan:
    context: str                 # 渲染好的 <recalled_memory>
    used_chars: int
    used_tokens: int
    decisions: tuple[MemorySelectionDecision, ...]
    # selected_memory_ids / rejected_memory_ids 由 decisions 派生
```

`max_chars` 与 `max_tokens` 必须分开：字符长度和分词后的 token 数不是一回事。

默认粗算（教学用，可复现，不冒充真账单）：

```python
def estimate_context_tokens(text: str) -> int:
    """Latin 词块 / 单个 CJK / 标点各计 1 个教学单位。"""
    return len(re.findall(r"[a-zA-Z0-9_]+|[\u3400-\u9fff]|[^\s]", text))
```

生产注入真 tokenizer：

```python
plan = select_memory_context(
    candidates,
    user_scope=current_scope,
    policy=policy,
    token_counter=target_model_tokenizer,  # 只影响装箱闸门
)
```

---

## 三层 authority：不是三个加分项

| Authority | 人话 | 例子 |
|-----------|------|------|
| `current_turn` | 就这一次你刚说的 | 「这次请用 Go」 |
| `workspace_override` | 本仓库局部约定 | 「自动化统一 TypeScript」 |
| `user_default` | 跨项目默认喜好 | 「我通常偏好 Python」 |

```text
current_turn > workspace_override > user_default
```

同层才比：`score ↓ → source_rank ↑ → captured_at 新 → memory_id`。  
未知 authority（如模型瞎写 `system_override`）→ **fail-closed 报错**。  
层级由 harness 注入；模型可以提议内容，不能给自己升权（生产可加签名/事件绑定防伪）。

### Authority ≠ Harness required

`current_turn` 只是偏好候选里的最高层。  
Base 指令 / 工具边界 / Working mode 是 **required `PromptSegment`**：任何偏好都挤不掉。required 自己装不下 → `PromptBudgetError`。

---

## 选择顺序为什么不能交换

`select_memory_context()` 固定顺序：

```text
1 scope_mismatch          跨用户再高分也拒
2 low_confidence          低于 min_score 默认弃权
3 authority 排队          过门后再排；不能绕过前两道门
4 duplicate_content       槽+正文都相同才去重（NFKC/大小写/空白归一）
5 authority_loser /
  conflict_loser          同槽竞争；败者不回填
6 top_k_reached /
  char|token_budget_exceeded /
  selected                原子装箱；过长可跳过，小 hit 可填
```

**同文不同槽不去重**：`preference:analysis-language` 与 `preference:automation-language` 即使都写「用 Python」，也是两回事。  
无 `conflict_key` 的候选只与同样无槽的去重。

原因码（9 种）：

```python
class MemoryDecisionReason(str, Enum):
    SELECTED = "selected"
    SCOPE_MISMATCH = "scope_mismatch"
    LOW_CONFIDENCE = "low_confidence"
    DUPLICATE_CONTENT = "duplicate_content"
    AUTHORITY_LOSER = "authority_loser"
    CONFLICT_LOSER = "conflict_loser"
    TOP_K_REACHED = "top_k_reached"
    CHAR_BUDGET_EXCEEDED = "char_budget_exceeded"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
```

真跑可见（教学 fixture）：`other-user` 0.99 → `scope_mismatch`；工作区 0.86 → `authority_loser`（输给本轮）；`weak-overlap` → `low_confidence`。

---

## 两层预算 + 两套日志

```text
Memory candidates
  └─ MemorySelectionPolicy → <recalled_memory>
       └─ plan_prompt(总 Prompt 预算) → 最终 system prompt
```

| 层 | 回答 | 你可能看到 |
|----|------|------------|
| Memory | 这几条记忆值不值得带出门？ | `selected=[...]`，`757/1200 chars` |
| 总 Prompt | 行李箱还塞不塞得下这整袋？ | `memory ... dropped`，`dropped=['memory']` |

**选中了 ≠ 最终进了系统提示。**  
`PROMPT_BUDGET_CHARS=1000` 时常见：第一层仍 selected，第二层整段 memory 被原子丢掉；`base`/`tools`/`mode` 仍在。

### 十类片段

| # | 片段 | 总预算策略 |
|---|------|------------|
| 1 | Base instructions | required |
| 2 | Identity | 可选，高价值 |
| 3 | Recalled memory | 可选，中等 |
| 4 | Project context | 可选，高价值 |
| 5 | Tool descriptions | required |
| 6 | Expert instructions | 可选，高价值 |
| 7 | Skill instructions | 可选，高价值 |
| 8 | Connector status | 可选，较低 |
| 9 | Regional conventions | 可选，低 |
| 10 | Working mode | required |

```python
@dataclass
class PromptSegment:
    name: str
    builder: Callable[[], str | None]
    condition: Callable[[], bool] = field(default=lambda: True)
    priority: int = 50            # 展示顺序：越小越靠前
    required: bool = False        # True = 预算不可删
    budget_priority: int = 50     # 抢座位：越大越优先
    provenance: str = "runtime"
```

**展示顺序 ≠ 预算价值**：mode 可以排在很后，但仍是 required。

总规划：

```text
构建片段 → 先预留 required → required 超预算则 PromptBudgetError
         → optional 按 budget_priority 尝试加入
         → 已选片段按 priority 渲染 → PromptPlan + SegmentDecision
```

---

## 运行时重组装与 clear

| 事件 | 影响 |
|------|------|
| 安装 recall 候选 | 重做 Memory 选择与 memory 片段 |
| 查询结束 / 切用户 | `clear_recalled_memory`，防泄漏 |
| 加载技能 / 切专家 / 切模式 / 连接器 | 对应片段重装 |
| 身份文件变更 | Identity |

存的是**候选**，不是上次拼好的死字符串。每次按当前 scope、policy、尺子重算。  
没命中时**不写空** `<memory>`。

---

## 动手：无 API Key

```bash
cd tracks/harness   # 或私人沙盒 learn-workbuddy-main
source .venv/bin/activate
python s15_prompt_assembly/code.py --demo
python s15_prompt_assembly/code.py
```

交互：

```text
memory          # 看 authority / 原因码 / 两层预算
memory clear    # memory 清空，防跨查询泄漏
```

看清「选中了却进不了总 Prompt」：

```bash
PROMPT_BUDGET_CHARS=1000 python s15_prompt_assembly/code.py
# memory → 第一层 selected；第二层 memory dropped；required 仍在
```

（README 示例 2000 往往仍装得下约 1532 字符；要用更紧的 1000 才能看见 dropped。）

---

## 常见误区

- 把 RecallHit 直接拼进 Prompt  
- 只保留 total score，说不清拒绝原因  
- 用输入顺序决定冲突（顺序一变事实翻转）  
- 高 score 覆盖高 authority  
- 让模型自行声明 authority  
- 把 `current_turn` 当成 required  
- 对长记忆直接切字符串（切断 provenance/XML）  
- 未命中还写空 `<memory>`  
- 把字符估算叫真实 token  
- 总预算不足就删除安全规则  
- 查询结束后不清 memory state  

---

## 面试题（问题 + 详细答案）

### 1. Retrieval / selection / packing / assembly 各解决什么？

**答：** 四段流水线，不能混成一步。

| 阶段 | 解决什么 | 不解决什么 |
|------|----------|------------|
| **Retrieval（检索，S12）** | 按 query 找到候选，打分、稳定排名，交出 `RecallResult` | 不决定最终进 Prompt 的名单 |
| **Selection（选择，S15 前半）** | 门禁 + authority + 去重 + 冲突，给每条 `selected/rejected` + 原因码 | 不重算检索分；不写回长期记忆 |
| **Packing（装箱）** | 在 top-k / 字符 / token 预算里装下存活候选；原子块，过长可跳过、小 hit 可填 | 不重新做 scope/冲突裁决 |
| **Assembly（组装）** | 把 `<recalled_memory>` 与其它 PromptSegment 按总预算拼成 system prompt | 不把 preference 升级成 required 安全规则 |

一句话：**找得到 ≠ 该用；该用 ≠ 装得下；装进记忆袋 ≠ 总行李箱还有空。**

---

### 2. 为何 scope、confidence 必须在去重/冲突/预算之前？

**答：** 前两道是**安全与质量门禁**，后面是「同类货怎么整理、怎么塞箱子」。

- **Scope 先做**：跨用户高分记忆若先参与去重/抢预算，会占满位子甚至进 Prompt → 泄漏。分再高也必须先 `scope_mismatch`。  
- **Confidence 先做**：低于 `min_score` 应默认弃权。若先装箱，预算一松噪声就会「排后面碰运气」混进来。  
- Authority / 去重 / 冲突 / 预算都假设：货已经是「这个用户的、够可信的」。  
- 注意：authority **不能绕过**前两道门——跨 scope 或低置信的「本轮」投影照样拒。

---

### 3. 为何 conflict 要显式槽，不能只靠字符串去重？

**答：** 正文相同 ≠ 同一事实；正文不同才可能争同一槽。

- **只按字符串去重**：两句都是「用 Python」，一个管「分析语言」、一个管「自动化语言」——会被误删，丢掉一个真实约束。  
- **显式 `conflict_key`**（如 `preference:automation-language`）：由上游结构化字段声明「争的是哪件事」；S15 不做第二次不可观察的「让模型判断矛不矛盾」。  
- 规则：同槽 + 同文 → 去重；同槽 + 异文 → 冲突；异槽 → 各走各的，即使正文一样也不去重。

---

### 4. 为何装箱允许小 hit 回填，冲突败者不允许？

**答：** 两种「没选上」含义不同。

| 情况 | 含义 | 能否回填 |
|------|------|----------|
| 某条太长 → `char/token_budget_exceeded` | 只是**太贵**，事实未被否决 | 可以：跳过它，继续装后面更小的 hit |
| 冲突 / authority 败者 | 同一事实槽已被赢家**裁决掉** | **不可以**：预算变松也不能让已被否定的事实溜回来 |

否则会出现：赢家因太长没装上，败者（错误偏好）反而进 Prompt。

---

### 5. 为何要两套 decision log？

**答：** 回答的问题不同，不能合成一本账。

| 日志 | 问题 | 例子 |
|------|------|------|
| Memory 选择日志 | 这几条记忆**值不值得带出门**？ | `selected=[python-current-turn, …]` |
| Segment 总预算日志 | **行李箱**还塞不塞得下这整袋？ | `memory ... dropped`，`dropped=['memory']` |

真跑 `PROMPT_BUDGET_CHARS=1000` 时常见：第一层仍 selected，第二层整段 memory 被原子丢掉；`base`/`tools`/`mode` 仍在。  
**选中了 ≠ 最终进了系统提示。**

---

### 6. 如何接真 tokenizer 而不破坏离线回归？

**答：** 尺子可插拔；门禁与排序契约不变。

1. `select_memory_context(..., token_counter=...)` 默认用教学 `estimate_context_tokens`（离线、确定、可复现）。  
2. 生产注入目标模型 tokenizer，只影响 **token 预算装箱** 谁被挤掉。  
3. **不改变**：scope / confidence / authority / 去重 / 冲突规则。  
4. **回归**：固定 candidates + scope + policy + **同一个** `token_counter`，跑两遍 `decisions` 应完全一致；对比「假尺 vs 真尺」时只换 counter，看 token 相关拒绝是否变化。

---

### 7. 语义去重如何仍保持可追踪 winner/loser？

**答：** 本章精确去重是教学底线；语义去重是上游增强，但审计形状不能丢。

- 可在 **S15 之前** 用 embedding cluster 合并「意思相近」的候选。  
- 合并时必须留下机器可读关系：谁是 winner、谁因 duplicate/semantic 被并掉、关联 id。  
- S15 仍输出完整 `decisions`（status + reason + `related_memory_id`），保证 **deterministic replay**：同一输入 → 同一胜负可解释，而不是黑盒「觉得像就删」。

---

### 8. 为何 authority 先于 score，又必须晚于两道门禁？

**答：** 两层「先」解决不同矛盾。

- **晚于 scope/confidence**：先保证货合法、够可信；非法高分本轮指令也不能靠升权绕过。  
- **先于 score（在过门之后）**：过门候选按 `本轮 > 工作区 > 默认` 排队；低层即使分更高也不能盖过高层。  
- **同层**才用 score / rank / 时间 / id 打破平局。  
- Authority 不是给分数乘权重，而是**权限仲裁**。

---

### 9. `current_turn` 与 required 片段的边界？

**答：** 都是「很重要」，但不是同一类东西。

| | `current_turn` | required PromptSegment |
|--|----------------|------------------------|
| 是什么 | 偏好候选里的最高层（本轮明确要求） | Harness 安全/工作边界：base、tools、mode 等 |
| 预算不够 | 仍可能整段 memory 被总预算 dropped | **先留位**；自己都装不下 → `PromptBudgetError` |
| 谁能盖过谁 | 可盖过 workspace / user_default | **任何 preference（含本轮）都挤不掉** |

口诀：**本轮说了算偏好；护照级规则（required）谁也扔不了。**  


---

## 练习方向（设计级）

1. 注入真 tokenizer，对比默认 estimator；固定输入证明 log 可复现  
2. 上游 `fact_type + subject` → 稳定 `conflict_key`  
3. 「必须保留」Memory ≠ required；预算不够不删 mode，应提示/fail-closed  
4. 用 reason 做 offline eval（如 scope 拒绝率 = mismatch/总数）  
5. authority 签名或事件绑定，防模型伪造层级  

---

## 边界与下一课

- 本章不重算检索分，不写回长期记忆  
- 教学粗算 ≠ 生产 tokenizer  
- 交互壳里的 bash/read/glob 只是演示入口，不是选择主课  

**下一课 s16**：按需加载 Skills，扩展知识不必从会话开始就常驻上下文。

---

## 你应该能回答

1. 召回到了为什么还不能直接进 Prompt？  
2. S12 和 S15 谁负责分数、谁负责进 Prompt？  
3. 三层 authority 顺序是什么？和 required 有何不同？  
4. 选择管道六步顺序？同文不同槽会怎样？  
5. 两套日志各回答什么？选中了为什么还会 dropped？  
6. `priority` 和 `budget_priority` 分别管什么？  
7. 为什么查询结束要 `memory clear`？  
