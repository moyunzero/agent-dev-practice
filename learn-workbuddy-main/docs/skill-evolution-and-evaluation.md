# Skill Evolution & Evaluation (Reference)

本文把上传资料里那篇技能综述（*Agent Skill Evaluation and Evolution:
Frameworks and Benchmarks*）压成一张给 `learn-workbuddy` 用的地图。它
回答两个 s16/s17 教程只碰了一半的问题：**技能怎么自动变好**，以及
**怎么判断一个技能是好是坏、是安全还是恶意**。

> 教程代码保持自包含。本文是可选深读，用于指导后续章节和你自己项目的
> skill 子系统设计。相关章节：s16（Skills）、s17（MCP）、s18（Experts）、
> s23（Audit/Sandbox）。

## 一、技能自进化的 4 种范式

`learn-workbuddy` 现在的技能是**静态**的：`SKILL.md` 写好放进目录，被
发现、被加载。真实系统里技能会**演化**。四条主流路线，各有代价：

| 范式 | 做法 | 优点 | 代价 | 对应章节 |
|---|---|---|---|---|
| 执行反馈 | 技能跑错/结果不对 → 自动定位并改 | 修问题准 | 只能被动补漏，没报错就不优化 | s09 transcript、s23 audit 提供反馈信号 |
| 轨迹蒸馏 | 把多次执行的完整流程提炼成通用步骤，固化为新技能 | 总结经验强 | 执行记录杂乱，易冗余、费资源 | s10 记忆蒸馏是同一手法的记忆版 |
| 压缩 & 整合 | 合并重复技能、精简描述、补缺漏 | 瘦身提效率 | 容易删掉关键步骤或安全规则 | s14 context compaction 的技能版 |
| 强化学习 | 任务成败当奖励，反复训练 | 跨任务复用强 | 算力大，且分不清是技能变好还是模型变强 | 超出教学 harness 范围，仅作认知 |

设计启示：前三种在一个纯 harness 里就能做（不训模型），是你项目里"把
用户重复任务一键固化成技能"功能的理论基础。压缩整合那条尤其要小心——
它是**安全规则被静默删除**的高发区，和下面的安全审计直接相关。

## 二、技能评测的 6 类基准

想在 README 里放"我的技能子系统好在哪"，得知道业界从哪 6 个维度量：

| 维度 | 测什么 | 代表基准 |
|---|---|---|
| 技能效用 (Utility) | 技能对任务完成率的实际提升 | SkillsBench（11 大领域）、SkillCraft（长时序工具调用/复用） |
| 技能生成 (Generation) | 自动生成技能的质量与复用能力 | SkillLearnBench |
| 检索与路由 (Retrieval & Routing) | 大规模技能库里的筛选、调度、多技能编排 | SkillRouter、SRA-Bench、AgentSkillOS |
| 安全审计 (Safety Auditing) | 恶意技能、运行时漏洞检测 | SkillTester、SkillGuardBench、SKILL-INJECT |
| 软件工程 (SWE) | 代码开发/运维场景下的技能 | SWE-SkillsBench |
| 真实环境 (Real-World) | 开放动态真实场景 | WildClawBench、SkillForge |

对教程最相关的两条：**检索与路由**直接对应 s16 的"技能多了以后选哪个"
——综述明确指出，仅靠名称/描述检索，准确率会大幅下降，这正是 s03 延迟
加载 + s16 索引匹配要解决的核心难题；**安全审计**对应 s16 现有的
P0/P1/P2 检查，但那套字符串匹配还远不够，见下一节。

## 三、SKILL-INJECT：三类技能注入攻击

s16 的 `audit_skill()` 保留 `rm -rf /`、`sudo`、`pip install` 这类直白模式
扫描，同时新增严格的声明式权限解析、权限升级 diff 与运行时门禁。但模式扫描本身
仍拦不住综述中 SKILL-INJECT 的三类隐蔽攻击：

1. **隐藏覆盖 (hidden override)**：技能表面人畜无害，实际悄悄覆盖或重定义
   了 harness 的默认行为/安全规则。对应"压缩整合"范式删掉安全规则的风险。
2. **伪装转移 (disguised transfer)**：把敏感操作伪装成正常步骤，或把数据
   在看似无关的步骤间转移出去（数据泄露）。
3. **远程引导 (remote guidance)**：技能在运行时从外部拉取指令，真正的恶意
   逻辑不在 `SKILL.md` 里，静态扫描当然看不到——这是 prompt injection 在
   技能层的变体。

这三类和 `docs/security-boundaries.md` 里"字符串匹配是安全带不是沙盒"的
结论完全一致：**技能审计必须超越模式匹配**，走向声明式权限 + 沙盒试跑 +
运行时出口管控。更稳妥的表述是：公开 agent / skill 生态里的供应链风险
已经足够说明，技能市场一旦开放，安全审计就必须成为一等能力。

## 四、给 learn-workbuddy 的落地建议

按性价比排序，不必全做：

1. **给 s16 的 `audit_skill` 补三类攻击的说明与检测占位**（已在 s16 README
   补充），让读者知道 P0/P1/P2 只是第一层。
2. **s16/s17 增加"声明式权限"字段**（已落地）：技能在 frontmatter 里声明
   工具/网络/路径；未知字段和越界路径 fail closed，新旧版本生成权限升级 diff，
   s17 在 `ToolSearch` 与 `DeferExecuteTool` 两阶段都执行 Connector trust 与
   Skill grant 的交集校验。
3. **轨迹蒸馏 → 新技能**（已在 example 落地）：保持 24 章主线不变，用
   `examples/self_evolving_skills/` 演示重复成功轨迹、held-out 回放、安全检查和
   人工审批后的版本化发布。
4. **评测意识**：README 里引用上面 6 类基准，说明本项目技能子系统对标的是
   哪几维（Utility + Retrieval/Routing + Safety），比空泛说"好用"有说服力。
   保持 24 章不变的离线基线已经落在
   [`examples/retrieval_routing_eval/`](../examples/retrieval_routing_eval/)：统一评价
   Skill、Memory、Reflection 的 Recall@K、MRR、拒答、作用域泄漏、权限泄漏与
   Prompt 预算，并把生命周期、权限和 prompt override 过滤放在相关性算分之前。

保持 24 章主线不变的可运行版本见
[`examples/self_evolving_skills/`](../examples/self_evolving_skills/)：它把成功 JSONL
轨迹蒸馏成候选 `SKILL.md`，通过 held-out 回放、安全检查和显式人工审批后才进入
版本化 Skill 库。

失败轨迹走另一条边界更严格的通道。可运行的
[`examples/reflection_memory/`](../examples/reflection_memory/) 要求相同失败签名至少由
两条独立轨迹支持，并提供一条显式关联的 held-out 成功恢复轨迹；形成的 Reflection
不包含原始命令或工具输出，也不拥有工具权限。它通过评测和人工批准后才能按任务族
注入 prompt，后续成功证据可将其标记为 `resolved`，同时保留版本与 provenance。

因此两个示例组成一条双通道学习边界：

```text
成功轨迹 + held-out 回放 -> 可执行 Skill 候选
重复失败 + 成功恢复       -> 非执行 Reflection 候选
```

这两个学习通道产生候选后，还要经过独立的检索路由考试：

```text
active + approved + scope/permission safe
  -> explainable rank
  -> top-k / prompt budget
  -> retrieval and safety metrics
```

## 来源

- *Agent Skill Evaluation and Evolution: Frameworks and Benchmarks*（综述）：
  https://arxiv.org/pdf/2606.11435 。基准名称与分类以该综述口径为准；具体数字按
  "综述口径 / 教学抽象"理解，不绑定某个私有实现。
- Voyager（skill library + 终生学习的开山论文，"轨迹蒸馏 → 技能库"路线的源头）：
  https://arxiv.org/abs/2305.16291
- datawhale《如何写出好的 Skill》（技能编写的中文实操指南）：
  https://github.com/datawhalechina/hello-agents/blob/main/Extra-Chapter/Extra08-%E5%A6%82%E4%BD%95%E5%86%99%E5%87%BA%E5%A5%BD%E7%9A%84Skill.md
