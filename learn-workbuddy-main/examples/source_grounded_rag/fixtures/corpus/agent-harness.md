# Agent Harness Operations

## Permission gate

Every tool call passes through a before-tool hook. The hook checks the declared tool name, normalized arguments, workspace scope, and the current user grant before execution.

Delete and publish operations require explicit approval. A relevance score never grants permission, and denied calls still emit an audit event.

## Audit trail

The after-tool hook records the result status and a bounded summary. Large outputs are stored as artifacts and referenced by digest instead of being copied into the transcript.
