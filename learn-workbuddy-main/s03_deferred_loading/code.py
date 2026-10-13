#!/usr/bin/env python3
"""s03_deferred_loading.py - discover, load, then execute deferred tools.

s02 made one registry the source of truth for model schemas and handlers.  This
lesson keeps that invariant and adds a visibility policy on top:

    compact directory -> ToolSearch -> loaded schema -> DeferExecuteTool

The catalog is static on purpose.  Deferred loading controls what enters one
model session; it is not a dynamic plugin installer.  The mock conversation is
offline so the complete data flow can be inspected without an API key.

Usage:
    python s03_deferred_loading/code.py
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import textwrap
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any


# Machine-readable learning path metadata. Tests enforce that every chapter
# declares what it inherits and what it adds.
PROGRESSION = {
    "chapter": "s03_deferred_loading",
    "builds_on": ["s02_tool_dispatch"],
    "adds": [
        "compact deferred tool directory",
        "deterministic tool discovery",
        "session-scoped schema loading",
    ],
    "preserves": ["single-source tool registry", "dispatch boundary"],
}

# Shared learning entrypoints: --demo is offline; --provider deepseek configures
# a real API environment before this standalone lesson loads.
import sys as _wb_sys
from pathlib import Path as _wb_Path

_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
if str(_WB_ROOT) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_WB_ROOT))
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo

_wb_maybe_run_chapter_demo(__file__, PROGRESSION)


# ═══════════════════════════════════════════════════════════════════
# Token Estimation
# ═══════════════════════════════════════════════════════════════════

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for JSON/mixed text."""
    return max(1, len(text) // 4)


def schema_tokens(schema: Mapping[str, Any]) -> int:
    """Estimate tokens for a tool schema (name + description + input_schema)."""

    return estimate_tokens(json.dumps(schema, ensure_ascii=False))


# ═══════════════════════════════════════════════════════════════════
# Tool Catalog and Session Loading State
# ═══════════════════════════════════════════════════════════════════

ToolHandler = Callable[..., str]


@dataclass(frozen=True)
class ToolEntry:
    """One immutable source for a tool's directory row, schema, and handler."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    handler: ToolHandler | None
    defer: bool  # True = expose only the directory row until ToolSearch loads it.

    def model_schema(self) -> dict[str, Any]:
        """Build a detached provider schema from the same entry used to execute."""

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": copy.deepcopy(dict(self.input_schema)),
        }

    @property
    def full_schema_tokens(self) -> int:
        return schema_tokens(self.model_schema())

    @property
    def directory_tokens(self) -> int:
        """Tokens for just name + brief description (the 'symbol table' entry)."""

        return estimate_tokens(f"{self.name}: {self.description}")


@dataclass(frozen=True)
class ToolMatch:
    """A stable search hit plus the schema that was loaded for this session."""

    name: str
    score: int
    schema: Mapping[str, Any]
    cache_hit: bool

    def to_payload(self) -> dict[str, Any]:
        """Return a model-readable result without exposing the catalog's schema."""

        return {
            "name": self.name,
            "score": self.score,
            "load_state": "cached" if self.cache_hit else "loaded",
            "schema": copy.deepcopy(dict(self.schema)),
        }


@dataclass(frozen=True)
class ToolSearchResult:
    """The complete, inspectable outcome of one ToolSearch call."""

    matches: tuple[ToolMatch, ...] = ()
    missing: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.matches)

    def render(self) -> str:
        """Encode success and misses as data the model can reason about."""

        lines: list[str] = []
        for match in self.matches:
            state = "cache hit" if match.cache_hit else "schema loaded"
            lines.append(
                f"✓ {match.name}: {state} ({schema_tokens(match.schema)} tokens, "
                f"score={match.score})"
            )
            lines.append(json.dumps(match.to_payload(), indent=2, ensure_ascii=False))
        lines.extend(f"✗ {name}: deferred tool not found" for name in self.missing)
        return "\n".join(lines) or "No deferred tools matched the request."


class ToolRegistry:
    """Own tool definitions and one session's deferred-schema activation state.

    - Immediate tools: full schema always in context
    - Deferred tools: compact directory row at startup, full schema after search

    Search and execution both resolve this same registry.  There is no second
    plugin map that can drift away from the model-visible contract.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ToolEntry] = {}
        # This cache is session state: it answers which schemas ToolSearch has
        # already placed in the transcript, not which tools exist globally.
        self._loaded_schemas: dict[str, dict[str, Any]] = {}

    # -- Registration --

    def register(
        self,
        name: str,
        schema: Mapping[str, Any],
        handler: ToolHandler | None,
        defer: bool = False,
        description: str = "",
    ) -> None:
        """Register one complete definition and reject ambiguous names early."""

        if not name:
            raise ValueError("tool name must not be empty")
        if name in self._tools:
            raise ValueError(f"duplicate tool name: {name}")
        schema_name = schema.get("name")
        if schema_name != name:
            raise ValueError(f"schema name {schema_name!r} does not match tool name {name!r}")
        input_schema = schema.get("input_schema")
        if not isinstance(input_schema, Mapping) or input_schema.get("type") != "object":
            raise ValueError(f"tool {name} must declare an object input schema")

        # Own a deep snapshot so later edits to the source constant cannot change
        # search results or the execution contract halfway through a session.
        self._tools[name] = ToolEntry(
            name=name,
            description=description or str(schema.get("description", "")),
            input_schema=copy.deepcopy(dict(input_schema)),
            handler=handler,
            defer=defer,
        )

    # -- Accessors --

    def get_immediate_schemas(self) -> list[dict[str, Any]]:
        """Full schemas for all immediate tools (always in context)."""

        return [entry.model_schema() for entry in self._tools.values() if not entry.defer]

    def get_deferred_directory(self) -> str:
        """Render the compact startup directory: name plus one-line purpose.

        This is what the model sees instead of full schemas.
        """

        return "\n".join(
            f"  - {entry.name}: {entry.description}"
            for entry in self._tools.values()
            if entry.defer
        )

    def get_deferred_names(self) -> list[str]:
        """Names of all deferred tools."""

        return [entry.name for entry in self._tools.values() if entry.defer]

    def get_immediate_names(self) -> list[str]:
        """Names whose full schemas are visible from the first model turn."""

        return [entry.name for entry in self._tools.values() if not entry.defer]

    def get_loaded_names(self) -> tuple[str, ...]:
        """Expose session activation without leaking the mutable cache."""

        return tuple(self._loaded_schemas)

    def loaded_schema_tokens(self) -> int:
        """Return the incremental context cost created by ToolSearch calls."""

        return sum(schema_tokens(schema) for schema in self._loaded_schemas.values())

    def get_handler(self, name: str) -> ToolHandler | None:
        """Get the handler for a tool (works for both immediate and deferred)."""

        entry = self._tools.get(name)
        return entry.handler if entry else None

    def is_deferred(self, name: str) -> bool:
        entry = self._tools.get(name)
        return entry.defer if entry else False

    # -- ToolSearch: discover and load deferred schemas on demand --

    def load_by_name(self, tool_names: Iterable[str]) -> ToolSearchResult:
        """Resolve exact deferred names, loading each full schema once."""

        matches: list[ToolMatch] = []
        missing: list[str] = []
        # Preserve caller order but collapse duplicate requests.  A repeated name
        # should not create repeated transcript payloads in the same result.
        for name in dict.fromkeys(tool_names):
            entry = self._tools.get(name)
            if entry is None or not entry.defer:
                missing.append(name)
                continue
            matches.append(self._load_match(entry, score=100))
        return ToolSearchResult(tuple(matches), tuple(missing))

    def search(self, queries: Iterable[str], top_k: int = 3) -> ToolSearchResult:
        """Rank deferred tools deterministically, then load only the top matches.

        This deliberately small scorer is inspectable teaching code, not a claim
        to replace a production BM25/vector index.  Exact name matches dominate,
        name-token matches outrank description matches, and name breaks score ties.
        """

        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        terms = _search_terms(queries)
        if not terms:
            return ToolSearchResult(missing=("<empty query>",))

        ranked: list[tuple[int, str, ToolEntry]] = []
        for entry in self._tools.values():
            if not entry.defer:
                continue
            score = _match_score(entry, terms)
            if score:
                ranked.append((score, entry.name, entry))

        # The explicit secondary key makes equal-score output independent of
        # registration or dictionary order, which keeps traces and tests stable.
        ranked.sort(key=lambda item: (-item[0], item[1]))
        if not ranked:
            return ToolSearchResult(missing=(" ".join(terms),))
        matches = tuple(
            self._load_match(entry, score)
            for score, _name, entry in ranked[:top_k]
        )
        return ToolSearchResult(matches=matches)

    def _load_match(self, entry: ToolEntry, score: int) -> ToolMatch:
        cache_hit = entry.name in self._loaded_schemas
        if not cache_hit:
            self._loaded_schemas[entry.name] = entry.model_schema()
        return ToolMatch(
            name=entry.name,
            score=score,
            schema=copy.deepcopy(self._loaded_schemas[entry.name]),
            cache_hit=cache_hit,
        )

    # -- Token Accounting --

    def token_report(self) -> dict[str, int]:
        """Calculate token usage for immediate vs deferred vs full loading."""

        immediate_tokens = sum(
            entry.full_schema_tokens for entry in self._tools.values() if not entry.defer
        )
        deferred_dir_tokens = sum(
            entry.directory_tokens for entry in self._tools.values() if entry.defer
        )
        full_tokens = sum(entry.full_schema_tokens for entry in self._tools.values())
        return {
            "immediate_tools": sum(1 for entry in self._tools.values() if not entry.defer),
            "deferred_tools": sum(1 for entry in self._tools.values() if entry.defer),
            "immediate_tokens": immediate_tokens,
            "deferred_dir_tokens": deferred_dir_tokens,
            "full_load_tokens": full_tokens,
            "current_tokens": immediate_tokens + deferred_dir_tokens,
            "saved_tokens": full_tokens - (immediate_tokens + deferred_dir_tokens),
            "saving_pct": round(
                (full_tokens - immediate_tokens - deferred_dir_tokens)
                / max(full_tokens, 1) * 100
            ),
        }


def _search_terms(queries: Iterable[str]) -> tuple[str, ...]:
    """Normalize free text into unique lowercase terms in caller order."""

    terms = (
        term
        for query in queries
        for term in re.findall(r"[a-z0-9]+", query.lower().replace("_", " "))
    )
    return tuple(dict.fromkeys(terms))


def _match_score(entry: ToolEntry, terms: tuple[str, ...]) -> int:
    """Score exact names, name tokens, then description tokens."""

    name = entry.name.lower()
    name_terms = set(name.replace("_", " ").split())
    description_terms = set(re.findall(r"[a-z0-9]+", entry.description.lower()))
    score = 0
    if "_".join(terms) == name or " ".join(terms) == name:
        score += 100
    for term in terms:
        if term in name_terms:
            score += 20
        elif term in name:
            score += 10
        if term in description_terms:
            score += 3
    return score


# ═══════════════════════════════════════════════════════════════════
# Mock Tool Handlers (no real side effects)
# ═══════════════════════════════════════════════════════════════════

def mock_read_file(path: str) -> str:
    return f"[MOCK] Read {path}: # Example\nprint('hello')\n"

def mock_write_file(path: str, content: str) -> str:
    return f"[MOCK] Wrote {len(content)} chars to {path}"

def mock_bash(command: str) -> str:
    return f"[MOCK] $ {command}\n(total 8\ndrwxr-xr-x  3 user  staff   96B Jul 8 10:00 src)"

def mock_glob(pattern: str) -> str:
    return f"[MOCK] Matches for '{pattern}':\nsrc/main.py\nsrc/utils.py"

def mock_image_gen(prompt: str, size: str = "1024x1024", style: str = "natural", seed: int | None = None) -> str:
    slug = prompt.lower().replace(" ", "_")[:30]
    return f"[MOCK] Generated image: {slug}.png ({size})"

def mock_image_edit(image_path: str, instruction: str, size: str | None = None) -> str:
    return f"[MOCK] Edited {image_path}: {instruction} → saved."

def mock_notebook_edit(notebook_path: str, cell_index: int, cell_type: str, source: str) -> str:
    return f"[MOCK] Edited cell {cell_index} ({cell_type}) in {notebook_path}"

def mock_lsp(operation: str, file_path: str, line: int | None = None, character: int | None = None) -> str:
    return f"[MOCK] LSP {operation} on {file_path}: 3 definitions found."

def mock_computer_use(action: str, coordinate: list = None, text: str = "") -> str:
    return f"[MOCK] ComputerUse: {action} at {coordinate or text}"

def mock_cron_create(name: str, rrule: str, prompt: str) -> str:
    return f"[MOCK] Created cron '{name}': {rrule}"

def mock_cron_list() -> str:
    return "[MOCK] Crons:\n  - daily_report: FREQ=DAILY\n  - weekly_sync: FREQ=WEEKLY"

def mock_enter_plan_mode() -> str:
    return "[MOCK] Entered plan mode."

def mock_exit_plan_mode() -> str:
    return "[MOCK] Exited plan mode."

# ═══════════════════════════════════════════════════════════════════
# Tool Schemas
# ═══════════════════════════════════════════════════════════════════

IMMEDIATE_TOOL_SCHEMAS = {
    "read_file": {
        "name": "read_file",
        "description": "Read the contents of a file.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    "write_file": {
        "name": "write_file",
        "description": "Write content to a file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    },
    "bash": {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    "glob": {
        "name": "glob",
        "description": "Find files matching a glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {"pattern": {"type": "string"}},
            "required": ["pattern"],
        },
    },
}

DEFERRED_TOOL_SCHEMAS = {
    "image_gen": {
        "name": "image_gen",
        "description": "Generate images from text descriptions using AI models. Supports various sizes and styles.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text description of the image to generate."},
                "size": {"type": "string", "enum": ["1024x1024", "1792x1024", "1024x1792"], "default": "1024x1024"},
                "style": {"type": "string", "enum": ["natural", "vivid"], "default": "natural"},
                "seed": {"type": "integer", "description": "Random seed for reproducibility."},
            },
            "required": ["prompt"],
        },
    },
    "image_edit": {
        "name": "image_edit",
        "description": "Edit or modify an existing image using AI models based on text instructions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Path to the source image."},
                "instruction": {"type": "string", "description": "What to change (e.g., 'add a sunset')."},
                "size": {"type": "string", "enum": ["1024x1024", "1792x1024"]},
            },
            "required": ["image_path", "instruction"],
        },
    },
    "notebook_edit": {
        "name": "notebook_edit",
        "description": "Replace the contents of a specific cell in a Jupyter notebook (.ipynb).",
        "input_schema": {
            "type": "object",
            "properties": {
                "notebook_path": {"type": "string"},
                "cell_index": {"type": "integer", "description": "Index of the cell to edit (0-based)."},
                "cell_type": {"type": "string", "enum": ["code", "markdown"]},
                "source": {"type": "string", "description": "New cell content."},
            },
            "required": ["notebook_path", "cell_index", "cell_type", "source"],
        },
    },
    "lsp": {
        "name": "lsp",
        "description": "Interact with Language Server Protocol servers for code intelligence (definitions, references, hover, diagnostics).",
        "input_schema": {
            "type": "object",
            "properties": {
                "operation": {"type": "string", "enum": ["definition", "references", "hover", "diagnostics"]},
                "file_path": {"type": "string"},
                "line": {"type": "integer"},
                "character": {"type": "integer"},
            },
            "required": ["operation", "file_path"],
        },
    },
    "computer_use": {
        "name": "computer_use",
        "description": "Control the desktop: mouse movement, clicks, keyboard input, and screenshots.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["screenshot", "mouse_move", "click", "type", "key"]},
                "coordinate": {"type": "array", "items": {"type": "integer"}, "description": "[x, y] pixel coordinates."},
                "text": {"type": "string", "description": "Text to type."},
            },
            "required": ["action"],
        },
    },
    "cron_create": {
        "name": "cron_create",
        "description": "Create a scheduled automation task with RFC 5545 RRULE recurrence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "rrule": {"type": "string", "description": "RFC 5545 recurrence rule, e.g., FREQ=DAILY"},
                "prompt": {"type": "string", "description": "Instruction to execute at each run."},
            },
            "required": ["name", "rrule", "prompt"],
        },
    },
    "cron_list": {
        "name": "cron_list",
        "description": "List all scheduled automation tasks.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    "enter_plan_mode": {
        "name": "enter_plan_mode",
        "description": "Enter plan mode to analyze and plan before executing.",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
}

DEFERRED_DESCRIPTIONS = {
    "image_gen": "Generate images from text descriptions using AI models.",
    "image_edit": "Edit or modify an existing image using AI models.",
    "notebook_edit": "Edit a specific cell in a Jupyter notebook.",
    "lsp": "Language Server Protocol code intelligence (definitions, references, etc.).",
    "computer_use": "Control the desktop: mouse, keyboard, screenshots.",
    "cron_create": "Create a scheduled automation task with RRULE recurrence.",
    "cron_list": "List all scheduled automation tasks.",
    "enter_plan_mode": "Enter plan mode to analyze before executing.",
}


# ═══════════════════════════════════════════════════════════════════
# Build the Registry
# ═══════════════════════════════════════════════════════════════════

def build_registry() -> ToolRegistry:
    """Create and populate the tool registry."""
    reg = ToolRegistry()

    # --- Immediate tools (schema always in context) ---
    reg.register("read_file", IMMEDIATE_TOOL_SCHEMAS["read_file"],
                 mock_read_file, defer=False)
    reg.register("write_file", IMMEDIATE_TOOL_SCHEMAS["write_file"],
                 mock_write_file, defer=False)
    reg.register("bash", IMMEDIATE_TOOL_SCHEMAS["bash"],
                 mock_bash, defer=False)
    reg.register("glob", IMMEDIATE_TOOL_SCHEMAS["glob"],
                 mock_glob, defer=False)

    # ToolSearch and DeferExecuteTool are themselves immediate tools
    # — they are the bridge to the deferred tools.
    toolsearch_schema = {
        "name": "ToolSearch",
        "description": (
            "Search for deferred tools by exact name or keyword. "
            "Returns the full JSON schema for matching tools. "
            "Use this before DeferExecuteTool to load the tool's schema."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "tool_names": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Exact tool names to look up.",
                },
                "queries": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Keywords for fuzzy search.",
                },
                "top_k": {"type": "integer", "default": 3},
            },
        },
    }
    defer_exec_schema = {
        "name": "DeferExecuteTool",
        "description": (
            "Execute a deferred tool by name. The tool's schema must have "
            "been loaded via ToolSearch first. Pass the tool name and its "
            "parameters."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "toolName": {"type": "string", "description": "Name of the deferred tool."},
                "params": {"type": "object", "description": "Parameters for the tool."},
            },
            "required": ["toolName"],
        },
    }
    reg.register("ToolSearch", toolsearch_schema, None, defer=False)
    reg.register("DeferExecuteTool", defer_exec_schema, None, defer=False)

    # --- Deferred tools (schema loaded on demand) ---
    deferred_handlers = {
        "image_gen": mock_image_gen,
        "image_edit": mock_image_edit,
        "notebook_edit": mock_notebook_edit,
        "lsp": mock_lsp,
        "computer_use": mock_computer_use,
        "cron_create": mock_cron_create,
        "cron_list": mock_cron_list,
        "enter_plan_mode": mock_enter_plan_mode,
    }
    for name, schema in DEFERRED_TOOL_SCHEMAS.items():
        reg.register(
            name, schema, deferred_handlers[name],
            defer=True,
            description=DEFERRED_DESCRIPTIONS.get(name, schema["description"][:80]),
        )

    return reg


# ═══════════════════════════════════════════════════════════════════
# Tool Handlers for ToolSearch and DeferExecuteTool
# ═══════════════════════════════════════════════════════════════════

def handle_tool_search(registry: ToolRegistry,
                       tool_names: list[str] | None = None,
                       queries: list[str] | None = None,
                       top_k: int = 3) -> str:
    """Discover deferred tools and place only matching schemas in the session."""

    if tool_names:
        return registry.load_by_name(tool_names).render()

    if queries:
        return registry.search(queries, top_k).render()

    return "Error: provide tool_names or queries."


def handle_defer_execute(registry: ToolRegistry,
                         toolName: str,
                         params: dict | None = None) -> str:
    """Execute a deferred tool only after ToolSearch exposed its contract."""

    params = params or {}
    handler = registry.get_handler(toolName)
    if handler is None:
        return f"Error: Unknown tool '{toolName}'"
    if not registry.is_deferred(toolName):
        return f"Error: '{toolName}' is immediate; call it directly."
    if toolName not in registry.get_loaded_names():
        return (
            f"Error: Schema for '{toolName}' not loaded. "
            "Call ToolSearch first."
        )
    try:
        return handler(**params)
    except Exception as exc:
        # Tool failures become observations; one bad handler must not tear down
        # the surrounding agent loop.
        return f"Error executing {toolName}: {exc}"


# ═══════════════════════════════════════════════════════════════════
# Mock LLM
# ═══════════════════════════════════════════════════════════════════

@dataclass
class MockResponse:
    """Simulates an LLM response with tool calls or text."""
    tool_calls: list[dict] = field(default_factory=list)
    text: str = ""
    stop_reason: str = "tool_use"  # or "end_turn"

    @property
    def is_tool_use(self) -> bool:
        return len(self.tool_calls) > 0


# Predefined mock responses: simulate a conversation where the model
# generates an image. The model knows from the deferred directory that
# "image_gen" exists, but doesn't have its schema yet.
MOCK_CONVERSATION = [
    MockResponse(
        tool_calls=[{
            "name": "ToolSearch",
            "input": {"tool_names": ["image_gen"]},
        }],
        stop_reason="tool_use",
    ),
    MockResponse(
        tool_calls=[{
            "name": "DeferExecuteTool",
            "input": {
                "toolName": "image_gen",
                "params": {
                    "prompt": "a cat sitting on a desk",
                    "size": "1024x1024",
                },
            },
        }],
        stop_reason="tool_use",
    ),
    MockResponse(
        text="图像已生成！文件名: a_cat_sitting_on_a_desk.png (1024x1024)\n"
             "如果你需要编辑这张图片，可以让我用 image_edit 工具修改。",
        stop_reason="end_turn",
    ),
]


class MockLLM:
    """Returns predefined responses in sequence."""

    def __init__(self, responses: list[MockResponse]):
        self._responses = list(responses)
        self._index = 0

    def chat(self, messages: list[dict]) -> MockResponse:
        if self._index >= len(self._responses):
            return MockResponse(text="(no more responses)", stop_reason="end_turn")
        resp = self._responses[self._index]
        self._index += 1
        return resp


# ═══════════════════════════════════════════════════════════════════
# Agent Loop (with deferred tool loading)
# ═══════════════════════════════════════════════════════════════════

# ANSI colors for logging
C_CYAN   = "\033[36m"
C_YELLOW = "\033[33m"
C_GREEN  = "\033[32m"
C_RED    = "\033[31m"
C_DIM    = "\033[90m"
C_RESET  = "\033[0m"
C_BOLD   = "\033[1m"


def agent_loop(registry: ToolRegistry, llm: MockLLM, user_query: str):
    """
    Agent loop with deferred tool loading.

    The loop itself is the same as s01/s02 — while stop_reason == "tool_use".
    The difference is in HOW tools are dispatched:
      - Immediate tools: direct call (same as s02)
      - Deferred tools: ToolSearch → DeferExecuteTool (two-step)
    """
    messages = [{"role": "user", "content": user_query}]
    turn = 0
    total_tool_calls = 0
    toolsearch_calls = 0
    deferexec_calls = 0

    while True:
        turn += 1
        response = llm.chat(messages)

        if not response.is_tool_use:
            # Model finished — print final text
            print(f"\n{C_GREEN}[Turn {turn}]{C_RESET} Model responds with text:")
            print(textwrap.indent(response.text, "  "))
            break

        # Process tool calls
        results = []
        for call in response.tool_calls:
            name = call["name"]
            params = call.get("input", {})
            total_tool_calls += 1

            if name == "ToolSearch":
                toolsearch_calls += 1
                tool_names = params.get("tool_names")
                queries = params.get("queries")
                print(f"\n{C_CYAN}[Turn {turn}] ToolSearch{C_RESET}")
                if tool_names:
                    print(f"  {C_DIM}tool_names={tool_names}{C_RESET}")
                if queries:
                    print(f"  {C_DIM}queries={queries}{C_RESET}")
                output = handle_tool_search(
                    registry, tool_names=tool_names, queries=queries,
                    top_k=params.get("top_k", 3),
                )
                # Log which schemas were loaded
                for line in output.split("\n"):
                    if line.startswith("✓"):
                        print(f"  {C_GREEN}{line}{C_RESET}")
                    elif line.startswith("✗"):
                        print(f"  {C_RED}{line}{C_RESET}")

            elif name == "DeferExecuteTool":
                deferexec_calls += 1
                tool_name = params.get("toolName")
                tool_params = params.get("params", {})
                print(f"\n{C_YELLOW}[Turn {turn}] DeferExecuteTool{C_RESET}")
                print(f"  {C_DIM}toolName={tool_name}{C_RESET}")
                print(f"  {C_DIM}params={json.dumps(tool_params, ensure_ascii=False)}{C_RESET}")
                output = handle_defer_execute(registry, toolName=tool_name, params=tool_params)
                print(f"  {C_GREEN}→ {output}{C_RESET}")

            else:
                # Immediate tool — direct dispatch (like s02)
                handler = registry.get_handler(name)
                print(f"\n{C_CYAN}[Turn {turn}] {name} (immediate){C_RESET}")
                if handler:
                    output = handler(**params)
                else:
                    output = f"Unknown tool: {name}"
                print(f"  {C_GREEN}→ {output}{C_RESET}")

            results.append({
                "type": "tool_result",
                "tool_name": name,
                "content": output,
            })

        messages.append({"role": "assistant", "content": results})

    return {
        "turns": turn,
        "total_tool_calls": total_tool_calls,
        "toolsearch_calls": toolsearch_calls,
        "deferexec_calls": deferexec_calls,
    }


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

def print_separator(title: str):
    print(f"\n{C_BOLD}{'=' * 60}{C_RESET}")
    print(f"{C_BOLD}  {title}{C_RESET}")
    print(f"{C_BOLD}{'=' * 60}{C_RESET}")


def interactive():
    """Interactive shell for manually trying ToolSearch and DeferExecuteTool."""
    print_separator("s03: Deferred Tool Loading Interactive")
    registry = build_registry()
    print("Commands:")
    print("  tools")
    print("  search <query>")
    print("  schema <tool_name>")
    print("  run <tool_name> <json_params>")
    print("  q")
    print("\nTry: search image")
    print("Try: schema image_gen")
    print('Try: run image_gen {"prompt":"a cat at a desk","size":"1024x1024"}')

    while True:
        try:
            line = input("s03 >> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line or line.lower() in {"q", "quit", "exit"}:
            return
        if line == "tools":
            print("Immediate:")
            for schema in registry.get_immediate_schemas():
                print(f"  - {schema['name']}")
            print("Deferred:")
            print(registry.get_deferred_directory())
            continue
        if line.startswith("search "):
            query = line[7:].strip()
            print(handle_tool_search(registry, queries=[query]))
            continue
        if line.startswith("schema "):
            name = line[7:].strip()
            print(handle_tool_search(registry, tool_names=[name]))
            continue
        if line.startswith("run "):
            _, rest = line.split("run ", 1)
            parts = rest.strip().split(" ", 1)
            tool_name = parts[0]
            raw_params = parts[1] if len(parts) > 1 else "{}"
            try:
                params = json.loads(raw_params)
            except json.JSONDecodeError as exc:
                print(f"Invalid JSON params: {exc}")
                continue
            print(handle_defer_execute(registry, toolName=tool_name, params=params))
            continue
        print("Unknown command. Use: tools | search <q> | schema <tool> | run <tool> <json> | q")


def main():
    print_separator("s03: Deferred Tool Loading")
    print("格言: 工具先列目录, schema 用到再展开")
    print("模式: ToolSearch → DeferExecuteTool (两步调用)\n")

    # -- Build registry --
    registry = build_registry()

    # -- Print token report --
    print_separator("Tool Registry Summary")

    report = registry.token_report()
    immediate_names = registry.get_immediate_names()
    deferred_names = registry.get_deferred_names()

    print(f"\n{C_BOLD}Immediate tools ({report['immediate_tools']}):{C_RESET}")
    print(f"  {', '.join(immediate_names)}")
    print(f"\n{C_BOLD}Deferred tools ({report['deferred_tools']}):{C_RESET}")
    print(f"  {', '.join(deferred_names)}")

    print(f"\n{C_BOLD}Token estimation:{C_RESET}")
    print(f"  Full loading (all schemas):     ~{report['full_load_tokens']:,} tokens")
    print(f"  Deferred loading (startup):      ~{report['current_tokens']:,} tokens")
    print(f"    ├─ immediate schemas:          ~{report['immediate_tokens']:,} tokens")
    print(f"    └─ deferred directory:         ~{report['deferred_dir_tokens']:,} tokens")
    saved = report['saved_tokens']
    pct = report['saving_pct']
    print(f"  {C_GREEN}Saved:                           ~{saved:,} tokens ({pct}% reduction){C_RESET}")

    # -- Print what the model sees at startup --
    print_separator("What the Model Sees at Startup")

    print(f"\n{C_DIM}# Immediate tool schemas (full):{C_RESET}")
    for schema in registry.get_immediate_schemas():
        print(f"{C_DIM}  - {schema['name']}: {schema['description'][:60]}{C_RESET}")

    print(f"\n{C_DIM}# Deferred tool directory (names only):{C_RESET}")
    directory = registry.get_deferred_directory()
    for line in directory.split("\n"):
        print(f"{C_DIM}{line}{C_RESET}")

    print(f"\n{C_DIM}# System prompt hint to model:{C_RESET}")
    print(f"{C_DIM}  The following tools are available but their schemas are NOT loaded.{C_RESET}")
    print(f"{C_DIM}  Use ToolSearch(tool_names=[...]) to load a tool's schema, then{C_RESET}")
    print(f"{C_DIM}  DeferExecuteTool(toolName=..., params=...) to execute it.{C_RESET}")

    # -- Run agent loop with mock LLM --
    print_separator("Agent Loop (mock LLM)")

    user_query = "帮我生成一张猫坐在桌子上的图片"
    print(f"\n{C_BOLD}User:{C_RESET} {user_query}")

    llm = MockLLM(MOCK_CONVERSATION)
    stats = agent_loop(registry, llm, user_query)

    # -- Print session summary --
    print_separator("Session Summary")

    # Recalculate tokens with loaded schemas
    loaded_schema_tokens = registry.loaded_schema_tokens()
    final_tokens = report["current_tokens"] + loaded_schema_tokens
    net_saved = report["full_load_tokens"] - final_tokens

    print(f"\n  Turns:                      {stats['turns']}")
    print(f"  Total tool calls:           {stats['total_tool_calls']}")
    print(f"    ├─ ToolSearch calls:      {stats['toolsearch_calls']}")
    print(f"    └─ DeferExecuteTool calls:{stats['deferexec_calls']}")
    print(f"\n  Token accounting:")
    print(f"    Startup cost (immediate + directory): ~{report['current_tokens']:,}")
    print(f"    Loaded via ToolSearch:                ~{loaded_schema_tokens:,}")
    print(f"    Total context from tools:             ~{final_tokens:,}")
    print(f"    Full loading would have cost:         ~{report['full_load_tokens']:,}")
    if net_saved > 0:
        net_pct = round(net_saved / report["full_load_tokens"] * 100)
        print(f"  {C_GREEN}Net saved:                              ~{net_saved:,} tokens ({net_pct}%){C_RESET}")
    else:
        print(f"  {C_RED}Net cost (more than full loading):      ~{-net_saved:,} tokens{C_RESET}")

    print(f"\n{C_BOLD}Key insight:{C_RESET} The agent only loaded schemas for tools it")
    print(f"actually used. If the conversation had stayed about file editing,")
    print(f"the {len(deferred_names)} deferred tool schemas would never have")
    print(f"entered the context at all.")

    # -- OS analogy --
    print_separator("OS Analogy: Dynamic Linking")
    print(f"""
  {C_BOLD}Static Visibility (s02){C_RESET}       {C_BOLD}Deferred Visibility (s03){C_RESET}
  ─────────────────────          ──────────────────────
  All schemas at startup         Only names at startup
  High memory, no lookup         Low memory, dlopen() on demand
  ToolSearch: not needed         ToolSearch: required
  DeferExecuteTool: not needed   DeferExecuteTool: required

  {C_DIM}ToolSearch   = resolve  — choose and expose a contract{C_RESET}
  {C_DIM}DeferExecute = call     — use the loaded contract{C_RESET}
  {C_DIM}Schema       = contract — model-visible invocation rules{C_RESET}
  {C_DIM}Tool name    = symbol   — compact discovery handle{C_RESET}
""")

    print("下一课: s04 Permission & Hooks — 先划边界, 再给自由\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deferred tool loading demo")
    parser.add_argument("--interactive", action="store_true", help="open an interactive ToolSearch shell")
    args = parser.parse_args()
    if args.interactive:
        interactive()
    else:
        main()
