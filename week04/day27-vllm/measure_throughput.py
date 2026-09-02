"""Day27 Lesson 3 — 对比串行 vs 并发请求的吞吐（需先 vllm serve :8027）。"""

from __future__ import annotations

import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

URL = "http://127.0.0.1:8027/v1/chat/completions"
MODEL = "mlx-community/Qwen2.5-0.5B-Instruct-4bit"
N = 8
MAX_TOKENS = 64


def one_request(i: int) -> tuple[float, int, int]:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": f"用不超过二十个字回答：什么是批处理？编号{i}"}],
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
        }
    ).encode()
    req = urllib.request.Request(
        URL, data=body, headers={"Content-Type": "application/json"}
    )
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    elapsed = time.perf_counter() - t0
    usage = data.get("usage") or {}
    return elapsed, int(usage.get("completion_tokens") or 0), int(
        usage.get("prompt_tokens") or 0
    )


def summarize(label: str, wall: float, rows: list[tuple[float, int, int]]) -> None:
    out_tok = sum(r[1] for r in rows)
    req_s = len(rows) / wall if wall > 0 else 0.0
    tok_s = out_tok / wall if wall > 0 else 0.0
    print(f"\n=== {label} ===")
    print(f"requests={len(rows)}  wall={wall:.2f}s")
    print(f"completion_tokens={out_tok}")
    print(f"throughput: {req_s:.2f} req/s  |  {tok_s:.1f} completion_tok/s")


def main() -> None:
    print(f"POST {URL}  N={N}  max_tokens={MAX_TOKENS}")

    seq_rows: list[tuple[float, int, int]] = []
    t0 = time.perf_counter()
    for i in range(N):
        seq_rows.append(one_request(i))
    summarize("sequential (one-by-one)", time.perf_counter() - t0, seq_rows)

    conc_rows: list[tuple[float, int, int]] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=N) as pool:
        futs = [pool.submit(one_request, i) for i in range(N)]
        for fut in as_completed(futs):
            conc_rows.append(fut.result())
    summarize(f"concurrent (workers={N})", time.perf_counter() - t0, conc_rows)

    print(
        "\n读数要点：wall 变短 + req/s 升高 → 引擎在用 continuous batching 吃并发；"
        "completion_tok/s 才是生成侧吞吐。"
    )


if __name__ == "__main__":
    main()
