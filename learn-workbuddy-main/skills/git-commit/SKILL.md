---
title: "Git Commit 规范提交"
summary: "规范化的 git commit 工作流，自动生成符合 Conventional Commits 的提交信息"
read_when:
  - 用户要求提交代码
  - 用户说 "commit"、"提交"、"check in"
  - 用户完成一个功能或修复后想保存进度
---

# Git Commit 技能

## 触发条件

当用户说以下内容时激活：
- "帮我提交代码"
- "commit 一下"
- "保存进度"
- "check in"

## 工作流程

### 1. 检查变更

```sh
git status
git diff --staged
git diff
```

### 2. 分析变更类型

根据变更内容判断类型：

| 类型 | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | 新增 API 端点 |
| `fix` | Bug 修复 | 修复空指针异常 |
| `docs` | 文档变更 | 更新 README |
| `style` | 代码格式 | 格式化、去尾部空格 |
| `refactor` | 重构 | 提取公共函数 |
| `test` | 测试 | 新增单元测试 |
| `chore` | 构建/工具 | 更新依赖版本 |

### 3. 生成提交信息

格式：`<type>(<scope>): <subject>`

```
feat(auth): 添加 OAuth2 登录支持

- 集成 Google 和 GitHub OAuth2 provider
- 添加 token 刷新机制
- 登录成功后重定向到 dashboard
```

### 4. 执行提交

```sh
git add <相关文件>
git commit -m "<提交信息>"
```

## 注意事项

- 提交信息用中文描述（除非用户指定英文）
- 一次提交只做一件事，不要混合多个不相关变更
- 不要提交 `.env`、密钥等敏感文件
- 如果 pre-commit hook 失败，先修复问题再提交
