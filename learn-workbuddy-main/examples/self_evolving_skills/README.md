# Self-Evolving Skills 离线示例

[返回首页](../../README.md)

> Harness 层：模型权重保持不变，把成功执行轨迹蒸馏成可审查、可评测、可审批和可回滚的外部 Skill。

## 代码架构图

```mermaid
flowchart LR
    T["JSONL trajectories"] --> G["Triage gate"]
    G --> D["Deterministic distillation"]
    D --> C["Candidate SKILL.md"]
    C --> E["Held-out replay + safety checks"]
    E --> H{"Human approval?"}
    H -->|No| Q["Keep candidate only"]
    H -->|Yes| V["Versioned skill library"]
    V --> A["Evolution audit"]
```

## 这个示例解决什么问题

s09 已经能保存完整执行轨迹，s10 能从追加式事实中蒸馏长期记忆，s16 能加载和创建 `SKILL.md`，s23 能记录审计证据。本示例把这些思想连成一个部署期学习闭环：

```text
成功轨迹 -> 候选技能 -> 独立评测 -> 人工批准 -> 版本化发布
```

它不是让 Agent 无约束地改写自己的 Prompt 或源码，也不训练模型参数。Agent 的“进化”发生在外部、可读、可 diff、可回滚的 Skill 库中。

## 安全与质量门禁

候选 Skill 必须依次满足：

1. 至少两条同类、成功且步骤一致的训练轨迹；
2. 失败轨迹不能成为 Skill 来源；
3. Skill 只保留通用意图、工具名和 provenance，不复制原始命令或工具输出；
4. 声明的工具必须与实际轨迹一致；
5. 一条未参与蒸馏的 held-out 轨迹必须成功复现相同步骤；
6. 内容必须通过基础危险操作、密钥和提示覆盖扫描；
7. 即使评测通过，没有显式 `approved_by` 也不能进入正式 Skill 库。

字符串扫描只是第一层教学防线，不等于沙盒。真实系统仍需要声明式权限、隔离试跑、网络出口控制和更强的 Skill 安全评测。

## 运行

只生成候选并完成评测，在人工审批门前停止：

```bash
python3 examples/self_evolving_skills/code.py
```

模拟用户明确批准，将候选发布为版本化 Skill：

```bash
python3 examples/self_evolving_skills/code.py --approve --approved-by alice
```

指定隔离目录：

```bash
python3 examples/self_evolving_skills/code.py \
  --home /tmp/learn-workbuddy-self-evolution \
  --approve \
  --approved-by alice
```

整个示例不需要 API key，也不会访问网络。

## 产物结构

```text
.tmp/self-evolving-skills/
├── traces/                         # 原始 JSONL 证据
├── candidates/<candidate-id>/
│   ├── candidate.json              # 结构化候选与 provenance
│   ├── SKILL.md                    # 尚未发布的候选
│   └── evaluation.json             # held-out 评测明细
├── skills/python-test-validation/
│   ├── manifest.json               # active_version + 历史版本
│   └── v1/SKILL.md                 # 人工批准后的正式版本
├── evolution-audit.jsonl           # 形成、评测、晋升事件
└── run_manifest.json               # 本轮演示清单
```

重复批准同一个 candidate 是幂等的，不会制造重复版本；由新证据产生的新 candidate 才会进入下一版本。

## 关键数据契约

| 对象 | 作用 |
|---|---|
| `Trajectory` | 带 `trace_id`、任务族、train/validation split、结果和 SHA-256 来源摘要的证据 |
| `SkillCandidate` | 由多条成功轨迹共同支持的候选步骤、工具权限和来源 ID |
| `EvaluationReport` | 每一项门禁的布尔结果，不用一个模糊总分隐藏失败原因 |
| `EvolutionStore` | 隔离保存证据、候选、评测、正式版本和审计事件 |
| `SkillEvolutionPipeline` | triage、distill、evaluate；不拥有跳过人工审批的权限 |

## 设计取舍

- **确定性蒸馏**：教学版要求多条轨迹具有相同的高层步骤，再提取共同流程。以后可以替换为 LLM distiller，但输出契约和门禁不变。
- **失败是教训，不是指令**：失败轨迹会被 triage 拒绝，不能直接发布成可执行 Skill。配套的 [`reflection_memory`](../reflection_memory/) 示例要求重复失败与成功恢复共同支持，再经评测和人工批准后写入独立的非执行 Reflection Memory。
- **评测与训练分离**：held-out trace 不属于 `source_trace_ids`，避免拿训练证据证明自己。
- **候选与发布分离**：通过评测只代表“可以提交审批”，不代表 Agent 有权安装。
- **原始证据不进 Skill**：减少密钥、用户数据、绝对路径和一次性命令被永久固化的风险。

## 验证

```bash
python3 -m pytest -q tests/test_self_evolving_skills.py
```

测试覆盖候选态停止、失败轨迹隔离、held-out 评测、显式审批、版本幂等和敏感轨迹拒绝。
