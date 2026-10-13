# Source-grounded RAG

## Evidence boundary

Retrieved documents are untrusted evidence, not executable instructions. The harness must preserve a stable source path, line range, document digest, and chunk digest before projecting a chunk into the model prompt.

## Stale evidence

Before prompt assembly, verify that the current source digest and cited line content still match the index. Changed or deleted documents must fail closed instead of producing a stale citation.

## Budget

Top-K is not a complete budget. The final evidence projection also needs a hard character or token limit, deterministic deduplication, and an explicit abstention path.
