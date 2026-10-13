# Progression Contract

本教程的代码不是 24 个孤立 demo，而是一条围绕桌面 Agent Harness 展开的渐进学习路径：每章继承上一章的稳定边界，只新增一个主要机制。`tests/test_project_structure.py` 会检查每个 `code.py` 都声明 `PROGRESSION` 元数据。

## 机器可检查规则

- 每章 `code.py` 必须定义 `PROGRESSION`。
- `chapter` 必须等于目录名。
- 除 s01 外，每章 `builds_on` 必须指向前一章。
- `adds` 和 `preserves` 必须非空。
- s24 必须把前面机制收束为一个完整 harness。

## 24 章渐进链路

| 章节 | 继承 | 本章新增 | 保留不变 |
|---|---|---|---|
| `s01_agent_loop` | 起点 | minimal agent loop<br>single bash tool<br>tool_use/tool_result feedback | interactive CLI |
| `s02_tool_dispatch` | s01_agent_loop | tool dispatch map<br>read/write/edit/glob tools<br>workspace path guard | same agent loop shape |
| `s03_deferred_loading` | s02_tool_dispatch | compact deferred tool directory<br>deterministic tool discovery<br>session-scoped schema loading | single-source tool registry<br>dispatch boundary |
| `s04_permission_hooks` | s03_deferred_loading | allow/ask/deny decisions<br>workspace path scope<br>separate user approval<br>auditable execution outcomes | multi-tool execution boundary<br>hook lifecycle |
| `s05_electron_shell` | s04_permission_hooks | main/renderer/preload split<br>IPC bridge<br>process isolation | agent request boundary |
| `s06_sidecar_server` | s05_electron_shell | sidecar control plane<br>JSON-RPC routing<br>ring buffer logs | desktop process boundary |
| `s07_session_management` | s06_sidecar_server | logical session and runtime separation<br>create/resume/close lifecycle<br>ACP-like HTTP boundary | sidecar-managed runtime |
| `s08_model_routing` | s07_session_management | lite/default/craft routing<br>cost tracking<br>agent-to-model mapping | session runtime context |
| `s09_jsonl_transcript` | s08_model_routing | sequenced transcript evidence<br>derived replay state<br>partial-tail recovery | model turn event shape |
| `s10_workspace_memory` | s09_jsonl_transcript | workspace-scoped fact log<br>policy-driven memory distillation<br>atomic curated memory view | append-only evidence and restart recovery |
| `s11_user_memory` | s10_workspace_memory | user-level memory<br>preference dedupe<br>identity prompt blocks | workspace memory layer |
| `s12_cloud_memory` | s11_user_memory | remote profile injection<br>history recall tool<br>memory selector | three-layer memory model |
| `s13_output_externalization` | s12_cloud_memory | large output threshold<br>tool-results swap files<br>page-fault reads | context budget mindset |
| `s14_context_compact` | s13_output_externalization | token pressure detection<br>structured compaction<br>summary preservation | externalized output pointers |
| `s15_prompt_assembly` | s14_context_compact | runtime prompt segments<br>budgeted context blocks<br>assembly order | memory and compaction inputs |
| `s16_skills_system` | s15_prompt_assembly | SKILL.md discovery<br>frontmatter parsing<br>on-demand skill loading | prompt assembly pipeline |
| `s17_mcp_connectors` | s16_skills_system | connector config<br>trust workflow<br>MCP tool namespace | lazy capability loading |
| `s18_experts_system` | s17_mcp_connectors | expert packages<br>expert prompt injection<br>session-level expert state | external capability model |
| `s19_visualizer` | s18_experts_system | visualizer protocol<br>SVG/HTML widget generation<br>theme-aware output | specialized output routing |
| `s20_result_presentation` | s19_visualizer | present_files flow<br>artifact cards<br>deliverable prioritization | visual output artifacts |
| `s21_sqlite_database` | s20_result_presentation | SQLite WAL database<br>session metadata<br>usage tracking | deliverable and session persistence |
| `s22_automation_scheduler` | s21_sqlite_database | RRULE scheduling<br>automation run history<br>runtime state table | SQLite persistence layer |
| `s23_audit_sandbox` | s22_automation_scheduler | hash-chain audit log<br>command safety classifier<br>sandbox policy | scheduled autonomous execution boundary |
| `s24_comprehensive` | s23_audit_sandbox | integrated mini harness<br>end-to-end agent pipeline<br>all-layer wiring | all previous chapter mechanisms |

## 读代码时怎么看

先看 `PROGRESSION["adds"]`，再搜索源码里的 `NEW in sXX`、`FROM sXX`、`LAYER` 注释。这样读者能区分：哪些是上一章留下来的 harness 骨架，哪些是本章新加的机制。
