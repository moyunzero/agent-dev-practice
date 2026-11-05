# 高频追问卡（Day59–60）

## 性能 · 客服 P99 升高

1. Grafana：是否全站、从何时起  
2. `request_id` + `duration_ms`：单次卡在哪  
3. 分路径：Postgres vs FAQ；Locust 复现对比  

口诀：大盘看面，日志看点。

## 故障 · 搜索一直超时（投研）

1. 只重试无兜底 → 搜集步空 → 整条断  
2. 重试扛偶发 + fixture/缓存降级 → 仍有可用文本  
3. 标明非实时；后续 context 可继续；中间稿可审计  

## 评估/幻觉

1. 客服：`source` = db / faq / need_human  
2. 投研：`intermediate/` 分步对账；不荐股、不编未查数字  
3. 降级注明非实时；有来源/交接物才算没瞎编  

