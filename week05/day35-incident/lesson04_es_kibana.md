# Day35 Lesson 4 — 加码 A：ES 存 JSON，Kibana 按字段搜

> 挂钩：本周日志主题 + 学员加码 A  
> **不**装 Logstash；用脚本把与请求日志同形状的 JSON 写入 ES（等价于「采集器吞了一行」）。

## ES / Kibana 各干什么

| 组件 | 干什么 |
|------|--------|
| **Elasticsearch** | 存文档、按字段建索引，支持 `status:500` 这类查询 |
| **Kibana** | 人用的搜/看界面（Discover） |
| **（本课用）seed_to_es.py** | 代替 Filebeat：把 3 条样例日志 PUT 进索引 `day35-logs` |

和 Day34 差在哪一步：Day34 只保证 **stdout 是 JSON**；本课多了 **进 ES + 能搜**。

## 端口（避让本机常用端口）

| 服务 | 宿主机 |
|------|--------|
| Elasticsearch | `19200` → 容器 9200 |
| Kibana | `15601` → 容器 5601 |

## 动手

```bash
cd week05/day35-incident

# 1) 起栈（首次拉镜像较慢；内存建议 Docker 至少给 2GB+）
docker compose up -d
docker compose ps
curl -s http://127.0.0.1:19200 | head

# 2) 写入 3 条样例（off / slow / error）
uv run python seed_to_es.py

# 3) 浏览器打开 Kibana
#    http://127.0.0.1:15601
#    Management → Data Views → Create：Index pattern = day35-logs*
#    Timestamp field 选 timestamp（若提示）
#    Discover 里过滤：status:500   或   fault:slow
```

**可选加深（不做也不挡过关）**：Filebeat 扫 uvicorn 日志文件；今天用 seed 已证明「JSON → ES → 按字段过滤」。

## 收工记得

```bash
docker compose down
```

（标 done 前会再清；学的过程中可先留着做掌握检查。）
