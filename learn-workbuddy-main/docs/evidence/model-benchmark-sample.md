# Model Benchmark Sample Report

This is a sanitized example of the real-model benchmark evidence format. Raw
benchmark runs live under `benchmark-runs/` and are ignored by git because they
can contain provider output, local paths, timing data, and prompts.

## What The Benchmark Checks

```sh
python3 scripts/model_benchmark.py --providers deepseek openai-chat
```

The suite creates isolated temp homes and runs:

| Provider | Cases |
|---|---|
| `deepseek` | mini harness, full tour, and `s01`-`s24` chapter eval traces. |
| `openai-chat` | mini harness, full tour, and `s01`-`s24` chapter eval traces through the provider adapter. |

Each chapter has its own interactive teaching CLI and a shared `--eval` entrypoint.
The benchmark uses `--eval` so every provider writes a comparable model/tool
trajectory under `benchmark-runs/<run>/traces/`.

## Required Pass Markers

| Case Type | Evidence Required |
|---|---|
| mini | `Audit verified: True` and `Transcript events:` |
| full | `RESULT: OK`, `provider_probe: true`, and audit verification |
| lesson | non-empty JSONL trace with `model_response`, `tool_call`, `tool_result`, and `case_end` events |

## Sanitized Example Summary

```text
total cases: 52
passed: 52
failed: 0
providers: deepseek, openai-chat
raw stdout: stored locally under benchmark-runs/<run>/stdout/
raw traces: stored locally under benchmark-runs/<run>/traces/
```

## Publication Rule

Do not commit raw benchmark output. If maintainers want to publish a result,
copy only the aggregate counts, provider families, case IDs, and remediation
notes. Remove:

- API keys or authorization headers
- model raw responses that may contain private prompts or paths
- local temp directories
- provider request IDs
- user-specific environment values

The benchmark is an engineering gate, not a claim about a proprietary product.
