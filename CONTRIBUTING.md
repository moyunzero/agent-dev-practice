# Contributing

感谢关注 **Agent Dev Practice**。本仓是 AgentGuide 开发岗路线的动手配套，欢迎 Issue 与 PR。

## 报告问题

请使用 [Bug Report 模板](.github/ISSUE_TEMPLATE/bug_report.md)，并尽量提供：

| 项 | 示例 |
|----|------|
| **Day 编号** | Week 2 / Day 12 |
| **目录** | `week02/day12-milvus/` |
| **环境** | macOS / Python 3.12 / Ollama 版本 |
| **已执行命令** | 完整复制终端命令 |
| **期望 vs 实际** | 截图或日志片段 |

## 提交 PR

1. Fork 本仓库，从 `main` 拉分支  
2. 改动范围尽量**单日目录**或**单篇 notes 文章**，避免大范围格式化  
3. 若改验收命令，请同步对应 `notes/weekXX/dayYY-*.md` 中的相同步骤  
4. PR 描述写明：修复哪 Day、复现步骤、验证方式  

### PR 自检

- [ ] 未提交 `.venv/`、`chroma_db/`、`.env`、密钥  
- [ ] 公开文档无个人学习日期（`YYYY-MM-DD`）  
- [ ] day README 未链接 `LEARN.md` 等私人文件  

## 内容贡献方向

- 修正教程中的错误或过时 API  
- 补充「常见问题」与边界说明  
- 改进某 day 的验收命令可读性  
- 英文 README 摘要（可选，欢迎单独 PR）  

## 维护者说明（本地）

本仓库维护者完成新 day 后，须**主动同步**公开文档（README、ROADMAP、day README、notes）。流程见本地 `docs/PUBLIC_SYNC.md`（不上传 GitHub）。

## License

贡献即表示同意 [MIT License](LICENSE)。
