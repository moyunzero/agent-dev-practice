# 全仓带学教法（强制）

> **适用范围：本仓库一切跟练轨道**，不限于 `learn-workbuddy-main/`。  
> 含：阶段① AgentGuide 每日 Day、阶段② learn-workbuddy、以及后续新增的任何学习目录 / 专题。  
> 与 [COACHING.md](./COACHING.md)、[MASTERY.md](./MASTERY.md)、[LEARNING_WORKFLOW.md](./LEARNING_WORKFLOW.md) 配套；**冲突时以上游强制目标 + COACHING/MASTERY 硬门禁为准**，本文提供统一教法。

教练开课默认遵循本文；轨道专用补充写在该目录说明里，**不得削弱**本文硬项。

---

## 三源合一（缺一不可）

每一课、每一个知识点（KP），必须同时用：

| 源 | 是什么 | 怎么用 |
|----|--------|--------|
| **① 真实代码** | 当日练习脚本 / `code.py` / demo | 走读真文件；只引 Read 过的片段；学员指认行 |
| **② 教案文档** | 上游路线目标句 + 当日 README / 官方文档 / 本目录讲义 | 挂钩原句；形状与易混点对齐教案；对外笔记对照教案 diff |
| **③ 真实情况** | 跑通命令、终端输出、小改再跑、失败复现 | 能跑则跑；抽问对齐「刚看到的行为」 |

```text
教案定「学什么」 → 代码定「怎么实现」 → 真跑定「实际长什么样」
三者对不上 → 先停，对齐后再抽问 / 前进。
```

**禁止：** 只讲口诀不打开代码；只讲代码丢掉教案机制/误区；整课零真跑且零小改；用写文章代替走读与真跑。  
**禁止：连环抽问冒充学会。** 学员能答对「会不会 / 能不能」却说「脑子里啥也没有」时，视为未掌握：停前进、回炉走读+指认+真跑，禁止靠下一题蒙混过关。

若某 KP 纯概念、无可执行 demo：③ 改为「对照教案失败路径 / 对照表，指到真实代码中的对应分支」，仍算真情况。

---

## 三个教学 skill（全仓启用）

| Skill | 本仓落点 | 职责 | 流水线 |
|-------|----------|------|--------|
| **explain-code-tutor** | `.cursor/skills/explain-code-tutor` | 真文件 Concept 走读；先形状后细节；一路径一洞察 | **C** |
| **codetrain**（lite 即可） | `.cursor/skills/codetrain-lite` | 小任务 + 提示阶梯；练习不贴完整答案；手撕拆 F 步 | **E / F** |
| **coding-tutor**（lite 即可） | `.cursor/skills/coding-tutor-lite` + 各轨进度记忆 | 已掌握 / 卡点 / 下一课从哪续 | **H** + 跨天开课 |

完整上游包可选（网络不稳可跳过；**纪律不减**）：

```bash
npx skills add https://github.com/envoydev/alfred-code --skill explain-code-tutor -g -y
npx skills add InferHaven/agent-skills --skill codetrain -g -y
npx skills add https://github.com/aojdevstudio/finance-guru --skill coding-tutor -g -y
```

### 诚实用法自检（每课结束；未勾不得标 mastered）

- [ ] explain-code-tutor：Read 真文件 + 一条主路径 + 一洞察  
- [ ] codetrain：有小改或 F 小步（若本日要求能改/手撕），且提示未贴完整答案  
- [ ] coding-tutor：已更新当日 LEARN + 该轨进度记忆（见下「进度落盘」）  

---

## 一课固定流水线（1 KP；顺序不可跳）

```text
A. 挂钩教案   亮出上游目标句 / 当日 README 对应小节（或官方文档锚点）
B. 形状       输入→输出 + 易混对比（先讲后考）；用语对齐教案
C. 走读代码   explain-code-tutor · Concept（真文件、一条路径、一洞察）
D. 指认       学员指着行口述；过关才进 E
E. 真跑/小改  至少其一（能跑优先）：跑 demo / 学员先预测再改一处再跑
F. 练习       codetrain（当日有「能改/手撕」时）；提示阶梯；禁止练习里贴完整答案
G. 抽问       一次一题；映射本 KP；尽量挂钩刚跑到的现象
H. 记账       coding-tutor：LEARN 状态 + 该轨进度记忆
```

**禁止：** 未走读就整类默写；填空代替走读；一条消息塞完原理+全文+多题+手撕；跳过 A 或跳过 E。

阶段①（AgentGuide Day）手撕力度按 [PROGRESS.md](../PROGRESS.md)「学员学习约束」：以口述 + 跟脚本小改为主，**不强制空白手撕整模块**；有小改时仍走 E/F 纪律。  
阶段②及后续深挖轨：章末「能写」拆成 ≥2 次 F 小步（见下）。

---

## 手撕怎么拆（深挖轨 / 明确要求「能写」时）

| 步 | 要求 | 过关 |
|----|------|------|
| F1…Fn | 每步约 5～15 行或一条分支 | 能讲清为何这样写 |
| 任一步不过 | 回到 C 走读对应函数 | 不前进 |

禁止一上来默写 40 行整 class。

---

## 对外笔记（后续每一章强制 · 不例外）

成稿标准见 [NOTE_QUALITY.md](./NOTE_QUALITY.md)。**从本章起，学完任何一轨/任何一天的对外笔记都必须同时满足：**

1. **心智可读**：有总图 / 易混对比 / 可复述短段（课堂真正立住的画面要写进文，不能只有考题答案）  
2. **教案不缩水**：对照当日上游教案（learn-workbuddy 各章 `README.md`、AgentGuide 当日资源、官方章节等）做 **目录级 diff**，至少覆盖：  
   - 开篇定位与架构图（或等价 Mermaid）  
   - 核心数据契约 / API 形状（该有代码块的要有）  
   - 机制分节（规则、失败路径、边界、生产对照、面试自问等——教案有的不得整段丢掉）  
   - 与上一章关系、今日边界  
3. **允许改写语气**（零基础、安检类比、注释口诀），**禁止**「只写课堂摘要 / 四步口诀」冒充成稿  
4. 学员说 ok 前：教练列出「相对 README 已覆盖的小节」自检；缺一块就补，不许先标 done  

learn-workbuddy 轨补充见 `learn-workbuddy-main/STAGE2_TEACHING.md`；**全仓新轨同样遵守本条。**

---

## 进度落盘（按轨）

> **全仓轨登记表**：[TRACKS.md](./TRACKS.md)（公开代码 / 笔记 / 同步清单）。下表只管带练落盘。

| 轨道 | LEARN | 进度真相源 | 续课记忆 | 公开代码 |
|------|-------|------------|----------|----------|
| 阶段① AgentGuide Day | `tracks/agentguide/weekXX/dayYY-*/LEARN.md` | 根目录 `PROGRESS.md` | 可写当日 LEARN「卡点」；跨天先读 PROGRESS | `tracks/agentguide/weekXX/dayYY-*/` |
| 阶段② harness | `learn-workbuddy-main/<章>/LEARN.md` | `learn-workbuddy-main/PROGRESS_STAGE2.md` | `learn-workbuddy-main/tutor-memory/CURRENT.md` | `tracks/harness/sXX_*/` |
| **未来新轨** | 该轨约定的 `LEARN.md`（或等价课表） | 该轨 `PROGRESS_*.md`（须在开课首日建好） | 该轨 `tutor-memory/` 或 PROGRESS 内「当前焦点」 | 建议 `tracks/<id>/` |

新开学习项目时：**先改 [TRACKS.md](./TRACKS.md) 加一行**，再补本表 + 根 README 入口，然后开第 1 课。不得只在子目录私自发明另一套带练法而架空本文。

轨道专用补充示例：`learn-workbuddy-main/STAGE2_TEACHING.md`（只写该轨差异，正文硬项以本文为准）。

---

## 与 COACHING 条款对照

| COACHING | 本文 |
|----------|------|
| §2.1 带读脚本 | C（explain-code-tutor） |
| §2.2 先讲后考 | B |
| §2.3 API 入参出参 | 走读点名；官方/锁定版本文档为准 |
| §2.4 提示不代做 | E/F（codetrain） |
| §2.5 掌握环 | LEARN + H（coding-tutor） |
| §1 上游对齐 | A（教案） |

---

## 收工检查（教练自检 · 全仓）

- [ ] A：挂钩过上游 / 当日教案原句  
- [ ] C：代码来自 Read 过的真文件  
- [ ] D：完成指认才进小改/练习  
- [ ] E：有真跑或小改再跑（或失败路径对照代码）  
- [ ] F：练习未贴完整答案（若有练习）  
- [ ] H：LEARN + 该轨进度记忆已更新  
- [ ] 未在同一条消息推进超过一个 KP  
- [ ] 对外笔记已对照教案 diff（收工写文时）  
- [ ] 三 skill 诚实用法自检三项均勾  
