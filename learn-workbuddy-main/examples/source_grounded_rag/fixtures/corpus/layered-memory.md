# 分层 Memory 约定

## Workspace Memory

项目事实属于 workspace scope。原始证据追加写入日志，经过验证的稳定事实才进入 curated view；检索命中本身不能自动写回长期记忆。

## User Memory

用户偏好必须按 user scope 隔离，并使用稳定 key 更新。相同 key 和 value 的重复写入应返回 unchanged，而不是制造重复记录。

## Compaction

会话摘要允许有损压缩，但 pending task、来源引用和已确认事实必须走 durable state 旁路，不能由摘要擅自关闭或改写。
