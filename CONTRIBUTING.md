# Contributing

感谢关注 **Agent Dev Practice**。本仓是两条学习轨的动手配套，欢迎 Issue 与 PR：

| 轨 | 上游 | 公开代码 | 长文 |
|----|------|----------|------|
| ① AgentGuide | [AgentGuide 开发岗](https://github.com/adongwanai/AgentGuide) | [`tracks/agentguide/`](tracks/agentguide/) | [`notes/weekXX/`](notes/) |
| ② Harness | [learn-workbuddy](https://github.com/adongwanai/learn-workbuddy) | [`tracks/harness/`](tracks/harness/) | [`notes/learn-workbuddy/`](notes/learn-workbuddy/) |

轨登记见 [`docs/TRACKS.md`](docs/TRACKS.md)。

## 报告问题

请使用 [Bug Report 模板](.github/ISSUE_TEMPLATE/bug_report.md)，并尽量提供：

| 项 | 轨①示例 | 轨②示例 |
|----|---------|---------|
| **编号** | Week 2 / Day 12 | s04 Permission Hooks |
| **目录** | `tracks/agentguide/week02/day12-milvus/` | `tracks/harness/s04_permission_hooks/` |
| **环境** | macOS / Python 3.12 / Ollama | Python 3.12；是否 `--demo` |
| **已执行命令** | 完整复制终端命令 | 同上 |
| **期望 vs 实际** | 截图或日志片段 | 同上 |

## 提交 PR

1. Fork 本仓库，从 `main` 拉分支  
2. 改动范围尽量**单日 / 单章目录**或**单篇 notes**，避免大范围格式化  
3. 若改验收命令，请同步对应长文里的相同步骤：  
   - 轨① → `notes/weekXX/dayYY-*.md`  
   - 轨② → `notes/learn-workbuddy/sXX-*.md`  
4. PR 描述写明：哪一轨、哪 Day/章、复现步骤、验证方式  

### PR 自检

- [ ] 未提交 `.venv/`、`chroma_db/`、`.env`、密钥、`learn-workbuddy-main/` 私人沙盒  
- [ ] 公开文档无个人学习日期（`YYYY-MM-DD`）  
- [ ] day / 章 README 未链接 `LEARN.md`、`PROGRESS.md`、`PROGRESS_STAGE2.md` 等私人文件  

## 内容贡献方向

- 修正教程中的错误或过时 API  
- 补充「常见问题」与边界说明  
- 改进某 day / 某章的验收命令可读性  
- 轨②：补齐 s05+ 公开切片（需与上游 clean-room / NOTICE 一致）  
- 英文 README 摘要（可选，欢迎单独 PR）  

## 维护者说明（本地）

完成新 day / 新章后，须**主动同步**公开文档：

- 轨①：根 README Day 索引、`docs/ROADMAP.md`、day README、`notes/weekXX/`  
- 轨②：`tracks/harness/` 索引与章 README、`notes/learn-workbuddy/`、根 README 双轨表  

流程见本地 `docs/PUBLIC_SYNC.md`（含 §Harness；不上传 GitHub）。全仓轨表：`docs/TRACKS.md`。

## License

贡献即表示同意 [MIT License](LICENSE)。Harness 切片另见 [`tracks/harness/NOTICE.md`](tracks/harness/NOTICE.md)。
