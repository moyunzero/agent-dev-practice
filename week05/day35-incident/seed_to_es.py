#!/usr/bin/env python3
"""把与 Day35 请求日志同形状的 JSON 写入 Elasticsearch（加码 A 验收用）。

用法（先 docker compose up -d，等 ES 健康）：
  uv run python seed_to_es.py
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

ES = "http://127.0.0.1:19200"
INDEX = "day35-logs"

DOCS = [
    {
        "event": "request_done",
        "path": "/ask",
        "method": "GET",
        "status": 200,
        "duration_ms": 1.2,
        "fault": "off",
        "q": "a",
        "request_id": "seed-off-1",
        "level": "info",
        "timestamp": "2026-09-04T06:00:00.000000Z",
    },
    {
        "event": "request_done",
        "path": "/ask",
        "method": "GET",
        "status": 200,
        "duration_ms": 2005.0,
        "fault": "slow",
        "q": "b",
        "request_id": "seed-slow-1",
        "level": "info",
        "timestamp": "2026-09-04T06:01:00.000000Z",
    },
    {
        "event": "request_done",
        "path": "/ask",
        "method": "GET",
        "status": 500,
        "duration_ms": 3.1,
        "fault": "error",
        "q": "c",
        "request_id": "seed-error-1",
        "level": "info",
        "timestamp": "2026-09-04T06:02:00.000000Z",
    },
]


def put_json(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()


def main() -> None:
    # 等 ES 可连
    urllib.request.urlopen(f"{ES}", timeout=5).read()

    # 简单索引（字段类型固定，便于 Kibana 过滤）
    try:
        put_json(
            f"{ES}/{INDEX}",
            {
                "mappings": {
                    "properties": {
                        "event": {"type": "keyword"},
                        "path": {"type": "keyword"},
                        "method": {"type": "keyword"},
                        "status": {"type": "integer"},
                        "duration_ms": {"type": "float"},
                        "fault": {"type": "keyword"},
                        "q": {"type": "keyword"},
                        "request_id": {"type": "keyword"},
                        "level": {"type": "keyword"},
                        "timestamp": {"type": "date"},
                    }
                }
            },
        )
    except urllib.error.HTTPError as e:
        if e.code != 400:
            raise
        # 索引已存在则忽略

    for i, doc in enumerate(DOCS):
        body = json.dumps(doc).encode()
        req = urllib.request.Request(
            f"{ES}/{INDEX}/_doc/{doc['request_id']}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(resp.status, doc["fault"], doc["status"])

    print(f"OK → 打开 Kibana http://127.0.0.1:15601")
    print(f"Data View 索引模式: {INDEX}*  ；过滤示例: status:500 或 fault:slow")


if __name__ == "__main__":
    main()
