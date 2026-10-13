# Pull Request 模板

## 变更描述

<!-- 简要描述这个 PR 做了什么 -->

## 变更类型

- [ ] 新增章节
- [ ] 修复内容错误
- [ ] 改进代码示例
- [ ] 改进 SVG 图表
- [ ] 翻译（EN/JA/KO）
- [ ] 其他

## 涉及章节

<!-- 列出修改了哪些章节，例如 s01, s05 -->

## 检查清单

- [ ] 代码可以独立运行（`python sXX/code.py`）
- [ ] README 中的"上一课/下一课"链接正确
- [ ] 没有引入新的外部依赖（或有充分理由）
- [ ] SVG 图表 viewBox 以 `0 0 800` 开头（如适用）
- [ ] 没有 hardcoded API key 或敏感信息
- [ ] 已运行 `python3 -m pytest -q`
- [ ] 已运行 `python3 scripts/verify.py`
- [ ] 没有加入闭源代码、私有 prompt、未脱敏路径或产品内部细节
