# Clean-room Boundary

This project teaches how to build a desktop AI assistant harness. It is inspired by observable patterns in modern agent products, including WorkBuddy-style desktop agents, but it is not a source-code clone.

## What is allowed

- Original Python implementations written for teaching.
- Architecture-level descriptions based on public behavior and generic engineering patterns.
- Redacted local observations such as directory categories, protocol shapes, and runtime concepts.
- Public standards and open ecosystems: HTTP, JSON-RPC, SSE, SQLite, Electron process architecture, MCP, JSONL, and ordinary tool-calling loops.
- Pseudocode that explains a concept without copying proprietary code structure.

## What is not allowed

- Proprietary source code, decompiled code, minified bundle excerpts, private prompts, or packaged assets.
- Product credentials, API keys, request credentials, account identifiers, local user paths, raw logs, or private workspace data.
- Instructions for bypassing licensing, authentication, sandboxing, or other security controls.
- Claims that require exact internal implementation knowledge unless they are softened into architecture-level observations.

## Wording rules

Use:

- "clean-room teaching implementation"
- "observable behavior"
- "architecture pattern"
- "ACP-like protocol"
- "history search abstraction"
- "production systems often..."

Avoid:

- "copied from source"
- "exact internal implementation"
- "reverse engineered source"
- exact private file names, offsets, hashes, build IDs, account IDs, or line numbers

## Evidence policy

Evidence notes in `docs/evidence/` are intentionally redacted. They are useful for explaining why a mechanism matters, not for proving or reproducing proprietary internals.

If a contribution depends on local inspection, rewrite it into one of these forms before opening a PR:

1. A generic architecture claim.
2. A public behavior users can observe without special access.
3. A teaching implementation that solves the same engineering problem differently.

When in doubt, remove the specific detail and keep the transferable idea.
