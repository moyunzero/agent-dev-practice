#!/usr/bin/env python3
from __future__ import annotations
"""
s08_model_routing.py - Model Routing & Cost Tiering

"Use AI to manage AI — cheap models do rough filtering,
 expensive models do reasoning."

    ┌──────────┐     ┌──────────────┐     ┌──────────────┐
    │  lite    │     │   default    │     │   craft      │
    │ $0.25/M  │     │   $3/M       │     │   $15/M      │
    │          │     │              │     │              │
    │ 粗筛/分类 │     │  规划/执行    │     │  推理/交互   │
    └──────────┘     └──────────────┘     └──────────────┘
         │                  │                    │
    memorySelector       Plan                CLI 主 Agent
    promptHookEval       general-purpose
    Explore              compact

The key insight: instead of putting everything into the expensive
model's context, use a cheap lite model to pre-filter. The expensive
model only sees the filtered results. Cost drops 10x, context
quality goes up.

This file simulates the routing with mock LLM responses — no API
key needed.

Usage:
    python s08_model_routing/code.py
"""



# Machine-readable learning path metadata. Tests enforce that every
# chapter declares what it inherits and what it adds.
PROGRESSION = {'chapter': 's08_model_routing',
 'builds_on': ['s07_session_management'],
 'adds': ['lite/default/craft routing', 'cost tracking', 'memory selector zero-tool routing'],
 'preserves': ['session runtime context']}

# Shared learning entrypoints: --demo is offline; --provider deepseek configures real API env.
import sys as _wb_sys
from pathlib import Path as _wb_Path
_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
if str(_WB_ROOT) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_WB_ROOT))
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo
_wb_maybe_run_chapter_demo(__file__, PROGRESSION)
import argparse
import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum

DEMO_SLEEP_SCALE = float(os.getenv("WORKBUDDY_DEMO_SLEEP_SCALE", "0.02"))


# ═══════════════════════════════════════════════════════════════
# Model Tier Enum — three cost levels
# ═══════════════════════════════════════════════════════════════

class ModelTier(Enum):
    """Three-tier model cost hierarchy, mirroring WorkBuddy's routing."""
    LITE = "lite"        # ~$0.25/M tokens — pre-filtering, classification
    DEFAULT = "default"  # ~$3/M tokens   — planning, execution, compression
    CRAFT = "craft"      # ~$15/M tokens  — user interaction, deep reasoning


# ═══════════════════════════════════════════════════════════════
# Model Info — per-tier cost/latency/capability parameters
# ═══════════════════════════════════════════════════════════════

@dataclass
class ModelInfo:
    """Parameters for each model tier."""
    tier: ModelTier
    name: str
    cost_per_million: float   # USD per 1M tokens
    latency_ms: int           # simulated response latency
    context_window: int       # max context tokens
    max_output: int           # max output tokens
    features: list[str]       # capability tags

    def cost(self, tokens: int, effort: str = "medium") -> float:
        """按 token 与 effort 档估算费用（教学用倍数，非厂商原价）。"""
        return tokens / 1_000_000 * self.cost_per_million * effort_cost_multiplier(effort)


# effort：同档内再分深度（README 练习 #2）
EFFORT_OPTIONS = frozenset({"low", "medium", "high"})
# 相对 medium 的费用/计费 token 倍数（示意：更深推理 ≈ 更贵）
EFFORT_COST_MULT: dict[str, float] = {
    "low": 0.7,
    "medium": 1.0,
    "high": 1.5,
}


def effort_cost_multiplier(effort: str) -> float:
    if effort not in EFFORT_COST_MULT:
        known = ", ".join(sorted(EFFORT_COST_MULT))
        raise ValueError(f"unknown effort {effort!r}; known: {known}")
    return EFFORT_COST_MULT[effort]


# Model registry — teaching abstraction of a tiered model matrix (illustrative, not a private config)
MODELS: dict[ModelTier, ModelInfo] = {
    ModelTier.LITE: ModelInfo(
        tier=ModelTier.LITE,
        name="lite (Lightweight)",
        cost_per_million=0.25,
        latency_ms=200,
        context_window=128_000,
        max_output=4_000,
        features=["cost_optimization"],
    ),
    ModelTier.DEFAULT: ModelInfo(
        tier=ModelTier.DEFAULT,
        name="default (Default)",
        cost_per_million=3.0,
        latency_ms=800,
        context_window=200_000,
        max_output=24_000,
        features=["tool_calling"],
    ),
    ModelTier.CRAFT: ModelInfo(
        tier=ModelTier.CRAFT,
        name="craft (Claude-4.0-Sonnet)",
        cost_per_million=15.0,
        latency_ms=2000,
        context_window=200_000,
        max_output=24_000,
        features=["reasoning", "vision", "tool_calling"],
    ),
}


# ═══════════════════════════════════════════════════════════════
# Agent → Model mapping table
# ═══════════════════════════════════════════════════════════════

# Which tier each agent uses — teaching abstraction based on the analysis
# notes' taxonomy, NOT extracted from any private source.
AGENT_MODEL_MAP: dict[str, ModelTier] = {
    # craft — direct user interaction
    "CLI":                    ModelTier.CRAFT,
    # default — planning, execution, compression
    "general-purpose":        ModelTier.DEFAULT,
    "Plan":                   ModelTier.DEFAULT,
    "compact":                ModelTier.DEFAULT,
    "contextSummary":         ModelTier.DEFAULT,
    "agentInstructions":      ModelTier.DEFAULT,
    "fork":                   ModelTier.DEFAULT,
    "statusline-setup":       ModelTier.DEFAULT,
    "Bash":                   ModelTier.DEFAULT,
    # lite — pre-filtering, classification, search
    "Explore":                ModelTier.LITE,
    "memorySelector":         ModelTier.LITE,
    "promptHookEvaluator":    ModelTier.LITE,
    "contentAnalyzer":        ModelTier.LITE,
    "terminalTitleGenerator": ModelTier.LITE,
    "summaryGenerator":       ModelTier.LITE,
    "insightsAnalyzer":       ModelTier.LITE,
}

MEMORY_SELECTOR_AGENT = "memorySelector"

# auto 模式：按任务类型选档（README 练习 #1），与 AGENT_MODEL_MAP 并行存在。
TASK_TIER_MAP: dict[str, ModelTier] = {
    "code_search": ModelTier.LITE,
    "explore": ModelTier.LITE,
    "memory_selection": ModelTier.LITE,
    "hook_eval": ModelTier.LITE,
    "plan": ModelTier.DEFAULT,
    "compress": ModelTier.DEFAULT,
    "user_chat": ModelTier.CRAFT,
    "complex_reasoning": ModelTier.CRAFT,
}

# 动态降级链：不可用时只往更便宜档走（README 练习 #4）
TIER_DOWNGRADE: dict[ModelTier, ModelTier | None] = {
    ModelTier.CRAFT: ModelTier.DEFAULT,
    ModelTier.DEFAULT: ModelTier.LITE,
    ModelTier.LITE: None,  # 已是最便宜，无处可降
}


# ═══════════════════════════════════════════════════════════════
# Memory Selector contract — bounded candidates, zero tools
# ═══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class MemoryCandidate:
    """One already-retrieved candidate offered to the selector.

    The selector does not own retrieval. It receives a bounded candidate set
    from a memory store or recall stage, then returns IDs from that set only.
    """

    memory_id: str
    content: str

    def __post_init__(self) -> None:
        if not self.memory_id.strip():
            raise ValueError("memory candidate ID must not be empty")
        if any(ch in self.memory_id for ch in ("[", "]", "\n")):
            raise ValueError(
                "memory candidate ID must not contain '[', ']', or newline"
            )
        if not self.content.strip():
            raise ValueError("memory candidate content must not be empty")


@dataclass(frozen=True)
class MemorySelectionRequest:
    """Provider-neutral input for one bounded memory selection decision."""

    query: str
    candidates: tuple[MemoryCandidate, ...]
    limit: int = 3

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("memory selection query must not be empty")
        if self.limit < 1:
            raise ValueError("memory selection limit must be positive")
        candidate_ids = [candidate.memory_id for candidate in self.candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("memory candidate IDs must be unique")


@dataclass(frozen=True)
class MemorySelectorRoute:
    """Observable invocation policy for the internal selector model."""

    model: ModelInfo
    tools: tuple[dict[str, object], ...] = ()
    max_output_tokens: int = 256
    temperature: float = 0.0
    reason: str = "bounded relevance selection over supplied memory candidates"

    def __post_init__(self) -> None:
        if self.tools:
            raise ValueError("memory selector route must not contain tools")


@dataclass(frozen=True)
class MemorySelectionResult:
    """Allowlisted selector output plus the route that produced it."""

    selected_ids: tuple[str, ...]
    considered_ids: tuple[str, ...]
    route: MemorySelectorRoute
    raw_response: str


# ═══════════════════════════════════════════════════════════════
# Mock LLM — simulates model responses without API calls
# ═══════════════════════════════════════════════════════════════

def mock_llm(
    model: ModelInfo,
    prompt: str,
    task: str = "",
    *,
    effort: str = "medium",
) -> str:
    """
    Simulate an LLM call. Returns a mock response based on the model tier.

    Real WorkBuddy calls the Anthropic API (or equivalent). Here we
    generate plausible-looking responses to demonstrate routing and
    cost differences without needing an API key.
    """
    # Simulate latency（high effort 略慢一点，教学示意）
    scale = {"low": 0.8, "medium": 1.0, "high": 1.3}.get(effort, 1.0)
    time.sleep(model.latency_ms / 1000 * DEMO_SLEEP_SCALE * scale)

    if task == "memory_selection":
        # The offline model only demonstrates the invocation contract. S12 owns
        # real candidate scoring; here we return bounded IDs from the supplied
        # list so S08 can focus on tier and tool routing.
        lines = [l.strip() for l in prompt.split("\n") if l.strip().startswith("[")]
        picked = lines[:3] if len(lines) >= 3 else lines
        picked_ids = [line.split("]", 1)[0] + "]" for line in picked]
        return "Selected memory IDs:\n" + "\n".join(picked_ids)

    if task == "hook_eval":
        # lite model: yes/no safety judgment
        return "SAFE: no sensitive content detected."

    if task == "explore":
        # lite model: file search results
        return "Found 3 relevant files:\n- src/auth.py\n- src/utils.py\n- tests/test_auth.py"

    if task == "plan":
        # default model: structured plan
        return ("Plan:\n"
                "1. Read src/auth.py to understand current login logic\n"
                "2. Identify the token validation bug\n"
                "3. Fix the validation function\n"
                "4. Run tests to verify")

    if task == "compact":
        # default model: context compression
        return ("[Compacted] User wants to fix login bug in src/auth.py. "
                "Previous discussion covered token validation issue.")

    # craft model: full reasoning response (user-facing)
    body = (
        f"Based on the analysis, the login bug in src/auth.py is caused by "
        f"an incorrect token expiration check. The fix is to compare the "
        f"expiration timestamp against the current time, not the token "
        f"creation time. I'll patch the validate_token() function."
    )
    return f"[effort={effort}] {body}"


# ═══════════════════════════════════════════════════════════════
# Cost Tracker — accumulate token costs per tier
# ═══════════════════════════════════════════════════════════════

@dataclass
class CostTracker:
    """Tracks token usage and cost per model tier."""
    # tokens consumed per tier
    tokens: dict[ModelTier, int] = field(default_factory=lambda: {
        ModelTier.LITE: 0, ModelTier.DEFAULT: 0, ModelTier.CRAFT: 0
    })
    # call count per tier
    calls: dict[ModelTier, int] = field(default_factory=lambda: {
        ModelTier.LITE: 0, ModelTier.DEFAULT: 0, ModelTier.CRAFT: 0
    })

    def track(self, tier: ModelTier, token_count: int):
        """Record a model call."""
        self.tokens[tier] += token_count
        self.calls[tier] += 1

    def total_cost(self) -> float:
        """Calculate total cost across all tiers."""
        return sum(
            MODELS[tier].cost(tokens)
            for tier, tokens in self.tokens.items()
        )

    def cost_by_tier(self) -> dict[ModelTier, float]:
        """Cost breakdown per tier."""
        return {
            tier: MODELS[tier].cost(tokens)
            for tier, tokens in self.tokens.items()
        }

    def reset(self):
        """Reset all counters."""
        for tier in self.tokens:
            self.tokens[tier] = 0
            self.calls[tier] = 0

    def summary(self) -> str:
        """Formatted cost summary table."""
        lines = []
        lines.append(f"  {'Tier':<12} {'Model':<30} {'Calls':<8} {'Tokens':<10} {'Cost':<12}")
        lines.append(f"  {'─'*12} {'─'*30} {'─'*8} {'─'*10} {'─'*12}")
        for tier in [ModelTier.LITE, ModelTier.DEFAULT, ModelTier.CRAFT]:
            model = MODELS[tier]
            tkns = self.tokens[tier]
            calls = self.calls[tier]
            cost = model.cost(tkns)
            lines.append(
                f"  {tier.value:<12} {model.name:<30} {calls:<8} "
                f"{tkns:<10} ${cost:<11.6f}"
            )
        lines.append(f"  {'─'*12} {'─'*30} {'─'*8} {'─'*10} {'─'*12}")
        lines.append(f"  {'TOTAL':<12} {'':30} {sum(self.calls.values()):<8} "
                     f"{sum(self.tokens.values()):<10} ${self.total_cost():<11.6f}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# ModelRouter — the core routing class
# ═══════════════════════════════════════════════════════════════

class ModelRouter:
    """
    Routes requests to different model tiers based on the agent.

    Real WorkBuddy uses model tags ("lite"/"default"/"craft") in
    agent definitions, resolved at runtime to concrete model IDs
    via user configuration. This teaching version maps directly.

    Usage:
        router = ModelRouter()
        model = router.route_request("memorySelector")  # → lite
        response = router.call("memorySelector", prompt, task="memory_selection")
    """

    def __init__(self):
        self.models = MODELS
        self.agent_map = AGENT_MODEL_MAP
        self.tracker = CostTracker()
        # 当前不可用的档（限流 / 宕机等）；空集 = 全部可用
        self.unavailable: set[ModelTier] = set()

    def set_unavailable(self, tier: ModelTier, *, down: bool = True) -> None:
        """标记某档不可用（down=True）或恢复（down=False）。"""
        if down:
            self.unavailable.add(tier)
        else:
            self.unavailable.discard(tier)

    def _resolve_with_fallback(self, preferred: ModelTier) -> ModelTier:
        """preferred 不可用则沿 TIER_DOWNGRADE 下探；lite 也挂则报错。"""
        tier = preferred
        visited: set[ModelTier] = set()
        while tier in self.unavailable:
            if tier in visited:
                raise RuntimeError(f"fallback cycle at {tier.value}")
            visited.add(tier)
            nxt = TIER_DOWNGRADE.get(tier)
            if nxt is None:
                raise RuntimeError(
                    f"{tier.value} unavailable and no cheaper fallback left"
                )
            tier = nxt
        return tier

    def route_request(
        self,
        agent_name: str,
        *,
        mode: str = "agent",
        task: str = "",
    ) -> ModelInfo:
        """按 Agent 映射或按任务类型（auto）选择模型档位。

        mode="agent"：查 AGENT_MODEL_MAP（默认，生产里更常见）。
        mode="auto"：查 TASK_TIER_MAP，必须提供 task；未知 task 报错。
        选定 preferred 后，若该档在 unavailable 集合里，则自动降到更便宜档。
        """
        if mode == "auto":
            if not task.strip():
                raise ValueError("auto mode requires a non-empty task type")
            if task not in TASK_TIER_MAP:
                known = ", ".join(sorted(TASK_TIER_MAP))
                raise ValueError(f"unknown task {task!r}; known: {known}")
            preferred = TASK_TIER_MAP[task]
        elif mode == "agent":
            preferred = self.agent_map.get(agent_name, ModelTier.DEFAULT)
        else:
            raise ValueError(f"unsupported routing mode: {mode!r}")
        return self.models[self._resolve_with_fallback(preferred)]

    def call(
        self,
        agent_name: str,
        prompt: str,
        task: str = "",
        token_override: int | None = None,
        *,
        mode: str = "agent",
        effort: str = "medium",
    ) -> str:
        """
        Simulate a model call for the given agent.

        Tracks cost automatically. Returns mock LLM response.
        """
        if agent_name == MEMORY_SELECTOR_AGENT:
            raise ValueError(
                "memorySelector must use MemorySelectorRouter.select(); "
                "the selector has a dedicated zero-tool contract"
            )
        model = self.route_request(agent_name, mode=mode, task=task)
        return self.call_model(
            model,
            prompt,
            task=task,
            token_override=token_override,
            effort=effort,
        )

    def call_model(
        self,
        model: ModelInfo,
        prompt: str,
        task: str = "",
        token_override: int | None = None,
        *,
        effort: str = "medium",
    ) -> str:
        """Call an already-routed model and account for its token cost."""

        # Estimate token count (in real life, tokenizer does this)
        if token_override is not None:
            tokens = token_override
        else:
            # Rough estimate: ~4 chars per token
            tokens = max(len(prompt) // 4, 500)

        # effort 越高，按倍数记更多「等效 token」（教学简化）
        billable = int(tokens * effort_cost_multiplier(effort))
        self.tracker.track(model.tier, billable)

        # Simulate the LLM call
        response = mock_llm(model, prompt, task, effort=effort)

        return response

    def print_routing_table(self):
        """Print the agent → model mapping table."""
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│                    Agent → Model 路由表                     │")
        print("├─────────────────────────┬──────────┬────────────────────────┤")
        print("│ Agent                   │ Tier     │ Model                  │")
        print("├─────────────────────────┼──────────┼────────────────────────┤")
        for agent, tier in sorted(self.agent_map.items()):
            model = self.models[tier]
            print(f"│ {agent:<23} │ {tier.value:<8} │ {model.name:<22} │")
        print("└─────────────────────────┴──────────┴────────────────────────┘")


class MemorySelectorRouter:
    """Route a memory relevance decision without creating a tool-capable Agent.

    A generic tool Agent may discover tools, execute them, and mutate external
    state. The memory selector has a narrower job: choose IDs from candidates
    that another layer already retrieved. Passing tool schemas is therefore a
    protocol error, not an optional optimization.
    """

    def __init__(self, router: ModelRouter):
        self.router = router

    def route(
        self,
        *,
        tool_schemas: Sequence[dict[str, object]] = (),
    ) -> MemorySelectorRoute:
        """Resolve the lite model while enforcing the zero-tool boundary."""

        if tool_schemas:
            raise ValueError("memory selector is zero-tool; tool schemas are not allowed")
        model = self.router.route_request(MEMORY_SELECTOR_AGENT)
        if model.tier is not ModelTier.LITE:
            raise RuntimeError("memory selector must remain on the lite model tier")
        return MemorySelectorRoute(model=model)

    @staticmethod
    def _build_prompt(request: MemorySelectionRequest) -> str:
        lines = [
            f"User query: {request.query.strip()}",
            f"Select up to {request.limit} candidate IDs.",
            "Return IDs only; do not answer the query or request tools.",
            "Candidates:",
        ]
        lines.extend(
            f"[{candidate.memory_id}] {candidate.content.strip()}"
            for candidate in request.candidates
        )
        return "\n".join(lines)

    @staticmethod
    def _allowlisted_ids(
        raw_response: str,
        request: MemorySelectionRequest,
    ) -> tuple[str, ...]:
        """Keep stable, unique IDs that were present in the input candidate set."""

        allowed = {candidate.memory_id for candidate in request.candidates}
        selected: list[str] = []
        for memory_id in re.findall(r"\[([^\]\n]+)\]", raw_response):
            if memory_id not in allowed or memory_id in selected:
                continue
            selected.append(memory_id)
            if len(selected) >= request.limit:
                break
        return tuple(selected)

    def select(
        self,
        request: MemorySelectionRequest,
        *,
        tool_schemas: Sequence[dict[str, object]] = (),
        token_override: int | None = None,
    ) -> MemorySelectionResult:
        """Run one selector call and return an ID-only, allowlisted result."""

        route = self.route(tool_schemas=tool_schemas)
        raw_response = self.router.call_model(
            route.model,
            self._build_prompt(request),
            task="memory_selection",
            token_override=token_override,
        )
        return MemorySelectionResult(
            selected_ids=self._allowlisted_ids(raw_response, request),
            considered_ids=tuple(
                candidate.memory_id for candidate in request.candidates
            ),
            route=route,
            raw_response=raw_response,
        )


# ═══════════════════════════════════════════════════════════════
# Demo 1: "Use AI to Manage AI" pattern
# ═══════════════════════════════════════════════════════════════

def demo_use_ai_to_manage_ai(router: ModelRouter):
    """
    Demonstrate the core pattern: lite model pre-filters, craft model
    processes the filtered results.

    Scenario: user asks about a previous bug fix. Instead of feeding
    all 10 memories to the expensive craft model, the lite model
    selects the 3 most relevant ones first.
    """
    print("\n" + "=" * 60)
    print("Demo: 用 AI 管理 AI — lite 粗筛, craft 推理")
    print("=" * 60)

    # S12/retrieval would supply this bounded candidate set. The offline mock
    # places the three relevant records first because S08 demonstrates routing,
    # not relevance scoring; the S12 recall chapter owns that algorithm.
    memories = (
        MemoryCandidate("mem_01", "Fixed login token expiration bug in auth.py"),
        MemoryCandidate("mem_05", "Fixed login race condition in session handling"),
        MemoryCandidate("mem_09", "Migrated authentication from JWT to session-based"),
        MemoryCandidate("mem_02", "Updated README to reflect new API endpoints"),
        MemoryCandidate("mem_03", "Refactored database connection pool logic"),
        MemoryCandidate("mem_04", "User prefers concise responses with code examples"),
        MemoryCandidate("mem_06", "Added unit tests for payment processing module"),
        MemoryCandidate("mem_07", "Configured CI/CD pipeline with GitHub Actions"),
        MemoryCandidate("mem_08", "Debugged memory leak in WebSocket handler"),
        MemoryCandidate("mem_10", "Optimized image loading with lazy loading strategy"),
    )

    user_query = "上次修那个登录 bug 的方案是什么？"

    # ── Step 1: lite model pre-filters ──
    print("\n┌─ Step 1: memorySelector (lite) 粗筛 ──────────────────────┐")
    print(f"│ 输入: {len(memories)} 条记忆 + 用户问题")
    print(f"│ 模型: {router.models[ModelTier.LITE].name}")
    print(f"│ 成本: ${router.models[ModelTier.LITE].cost_per_million}/M tokens")

    selector = MemorySelectorRouter(router)
    selection = selector.select(
        MemorySelectionRequest(user_query, memories, limit=3),
        token_override=5000,
    )

    print(f"│ 工具: {len(selection.route.tools)}（zero-tool）")
    print(f"│ 输出: {list(selection.selected_ids)}")
    print(f"│ tokens: 5000, cost: ${router.models[ModelTier.LITE].cost(5000):.6f}")
    print("└──────────────────────────────────────────────────────────┘")

    # The main Agent receives the selected records, never the selector's free
    # text or any hallucinated ID outside the supplied candidate set.
    selected_memories = [
        f"[{candidate.memory_id}] {candidate.content}"
        for candidate in memories
        if candidate.memory_id in selection.selected_ids
    ]

    # ── Step 2: craft model processes filtered results ──
    print("\n┌─ Step 2: CLI (craft) 推理 ────────────────────────────────┐")
    print(f"│ 输入: {len(selected_memories)} 条相关记忆 + 用户问题")
    print(f"│ 模型: {router.models[ModelTier.CRAFT].name}")
    print(f"│ 成本: ${router.models[ModelTier.CRAFT].cost_per_million}/M tokens")

    craft_prompt = f"User query: {user_query}\n\nRelevant memories:\n"
    craft_prompt += "\n".join(selected_memories)

    answer = router.call("CLI", craft_prompt, token_override=5000)

    print(f"│ 回答: {answer[:80]}...")
    print(f"│ tokens: 5000, cost: ${router.models[ModelTier.CRAFT].cost(5000):.6f}")
    print("└──────────────────────────────────────────────────────────┘")

    # ── Cost comparison ──
    lite_cost = router.models[ModelTier.LITE].cost(5000)
    craft_cost = router.models[ModelTier.CRAFT].cost(5000)
    total = lite_cost + craft_cost

    # What if we fed all 10 memories to craft directly?
    all_craft_cost = router.models[ModelTier.CRAFT].cost(20000)

    print(f"\n┌─ 成本对比 ────────────────────────────────────────────────┐")
    print(f"│ 分级路由 (lite + craft):  ${total:.6f}")
    print(f"│ 全 craft (10条记忆全量):  ${all_craft_cost:.6f}")
    print(f"│ 节省:                     ${all_craft_cost - total:.6f} "
          f"({(1 - total/all_craft_cost)*100:.0f}%)")
    print(f"└──────────────────────────────────────────────────────────┘")


# ═══════════════════════════════════════════════════════════════
# Demo 2: Cost comparison — all-craft vs tiered routing
# ═══════════════════════════════════════════════════════════════

def demo_auto_routing(router: ModelRouter):
    """README 练习 #1：按任务类型 auto 选档（与 Agent 硬编码映射对照）。"""
    print("\n", "=" * 60)
    print("Demo: auto 模式 — 按任务类型选档（README 练习 #1）")
    print("=" * 60)
    print("\n同一「Worker」名字，换 task，档位应跟着变：")
    samples = [
        ("code_search", "搜代码 / 过滤"),
        ("plan", "做计划"),
        ("user_chat", "直接回用户"),
    ]
    for task, desc in samples:
        model = router.route_request("Worker", mode="auto", task=task)
        print(f"  task={task:<18} → {model.tier.value:<8}  ({desc})")

    # 对照：仍按 Agent 名时，未知 Worker 会落到 default
    agent_fallback = router.route_request("Worker", mode="agent")
    print(f"\n  mode=agent、未知 Agent「Worker」→ {agent_fallback.tier.value}（回落 default）")
    print("  要点: auto 看任务；agent 看角色名。生产里多数 Agent 仍显式绑档更稳。")


def demo_effort(router: ModelRouter):
    """README 练习 #2：同档 craft，effort 再拧成本/深度。"""
    print("\n", "=" * 60)
    print("Demo: effort — 同档再分 low / medium / high（README 练习 #2）")
    print("=" * 60)
    tokens = 5_000
    craft = router.models[ModelTier.CRAFT]
    print(f"\n固定模型: {craft.name}  |  原始 tokens={tokens}")
    print(f"  {'effort':<10} {'倍数':>6}  {'计费tokens':>12}  {'费用':>12}")
    print(f"  {'─'*10} {'─'*6}  {'─'*12}  {'─'*12}")
    for effort in ("low", "medium", "high"):
        mult = effort_cost_multiplier(effort)
        billable = int(tokens * mult)
        cost = craft.cost(tokens, effort=effort)
        print(f"  {effort:<10} {mult:>6.1f}  {billable:>12}  ${cost:>11.6f}")
    print("\n  要点: 档位选「哪台车」；effort 选「这台车踩多深油门」。")
    print("  教学倍数: low=0.7 / medium=1.0 / high=1.5（示意，非厂商原价）。")


def demo_fallback(router: ModelRouter):
    """README 练习 #4：某档不可用时只往更便宜档降。"""
    print("\n", "=" * 60)
    print("Demo: 动态降级 — craft 挂了怎么办（README 练习 #4）")
    print("=" * 60)

    router.unavailable.clear()
    preferred = router.route_request("CLI")
    print(f"\n  正常: CLI → {preferred.tier.value}")

    router.set_unavailable(ModelTier.CRAFT)
    after = router.route_request("CLI")
    print(f"  craft 限流后: CLI → {after.tier.value}（降一级）")

    router.set_unavailable(ModelTier.DEFAULT)
    deeper = router.route_request("CLI")
    print(f"  craft+default 都挂: CLI → {deeper.tier.value}（再降）")

    router.set_unavailable(ModelTier.LITE)
    try:
        router.route_request("CLI")
        print("  三档全挂: 未报错（异常）")
    except RuntimeError as exc:
        print(f"  三档全挂: RuntimeError → {exc}")

    router.unavailable.clear()
    print("  已恢复全部档位。要点: 只降不升；lite 也挂就硬失败。")


def demo_cost_comparison(router: ModelRouter):
    """
    Simulate a full conversation: user asks to explore a project and
    fix a bug. Compare cost of all-craft vs tiered routing.
    """
    print("\n", "=" * 60)
    print("Demo: 成本对比 — all-craft vs 分级路由")
    print("=" * 60)

    # Simulated conversation steps: (agent, task, tokens)
    steps = [
        ("Explore",              "explore",     8000),   # search files
        ("Plan",                 "plan",       15000),   # analyze architecture
        ("memorySelector",       "memory_selection", 5000),  # find memories
        ("promptHookEvaluator",  "hook_eval",   2000),   # eval hooks
        ("CLI",                  "",           20000),   # fix the bug
    ]

    # ── Scenario A: all craft (no routing) ──
    router.tracker.reset()
    all_craft_latency_ms = 0
    print("\n─ Scenario A: 全部使用 craft 模型 ─")
    for agent, _task, tokens in steps:
        # Force all to craft
        router.tracker.track(ModelTier.CRAFT, tokens)
        # Simulate response
        model = router.models[ModelTier.CRAFT]
        all_craft_latency_ms += model.latency_ms
        time.sleep(model.latency_ms / 1000 * DEMO_SLEEP_SCALE)
        print(f"  {agent:<25} → craft  {tokens:>6} tokens  "
              f"${model.cost(tokens):.6f}")

    craft_tracker = CostTracker()
    craft_tracker.tokens = dict(router.tracker.tokens)
    craft_tracker.calls = dict(router.tracker.calls)

    # ── Scenario B: tiered routing ──
    router.tracker.reset()
    tiered_latency_ms = 0
    print("\n─ Scenario B: 分级路由 ─")
    for agent, _task, tokens in steps:
        model = router.route_request(agent)
        router.tracker.track(model.tier, tokens)
        tiered_latency_ms += model.latency_ms
        time.sleep(model.latency_ms / 1000 * DEMO_SLEEP_SCALE)
        print(f"  {agent:<25} → {model.tier.value:<8} {tokens:>6} tokens  "
              f"${model.cost(tokens):.6f}")

    tiered_cost = router.tracker.total_cost()
    all_craft_cost = craft_tracker.total_cost()

    # ── Comparison table ──
    print(f"\n┌─ 结果对比 ────────────────────────────────────────────────┐")
    print(f"│                          {'全 craft':>14}  {'分级路由':>14}  │")
    print(f"│  {'总 tokens':<22}  {sum(craft_tracker.tokens.values()):>14}  "
          f"{sum(router.tracker.tokens.values()):>14}  │")
    print(f"│  {'总成本':<22}  ${all_craft_cost:>12.6f}  ${tiered_cost:>12.6f}  │")
    print(f"│  {'总延迟(ms)':<22}  {all_craft_latency_ms:>14}  "
          f"{tiered_latency_ms:>14}  │")
    print(f"│  {'延迟差(ms)':<22}  {'—':>14}  "
          f"{all_craft_latency_ms - tiered_latency_ms:>14}  │")
    print(f"│  {'节省':<22}  {'—':>14}  "
          f"${all_craft_cost - tiered_cost:>12.6f}  │")
    print(f"│  {'节省比例':<22}  {'—':>14}  "
          f"{(1-tiered_cost/all_craft_cost)*100:>13.1f}%  │")
    print(f"└──────────────────────────────────────────────────────────┘")


# ═══════════════════════════════════════════════════════════════
# Demo 3: Agent loop — different agents get different models
# ═══════════════════════════════════════════════════════════════

def demo_agent_loop(router: ModelRouter):
    """
    Simulate a mini agent loop: user sends a message, multiple agents
    fire in sequence, each using its assigned model tier.
    """
    print("\n", "=" * 60)
    print("Demo: Agent 循环 — 不同 Agent 使用不同模型")
    print("=" * 60)

    user_message = "帮我看看这个项目的架构，然后修复 src/auth.py 里的登录 bug"

    print(f"\n用户: {user_message}")
    print()

    # Simulated pipeline: each agent does its part
    pipeline = [
        ("promptHookEvaluator",  "hook_eval",          "检查输入安全性"),
        ("memorySelector",       "memory_selection",   "检索相关记忆"),
        ("Explore",              "explore",            "搜索代码库"),
        ("Plan",                 "plan",               "制定修复计划"),
        ("CLI",                  "",                   "执行修复并回复用户"),
    ]

    router.tracker.reset()
    selector = MemorySelectorRouter(router)

    for agent, task, desc in pipeline:
        model = router.route_request(agent)
        # Simulate token count based on task
        token_map = {
            "hook_eval": 2000,
            "memory_selection": 5000,
            "explore": 8000,
            "plan": 15000,
            "": 20000,
        }
        tokens = token_map.get(task, 5000)

        print(f"  ┌─ {agent} ({model.tier.value})")
        print(f"  │  任务: {desc}")
        print(f"  │  模型: {model.name}")
        print(f"  │  延迟: {model.latency_ms}ms")

        if agent == MEMORY_SELECTOR_AGENT:
            selection = selector.select(
                MemorySelectionRequest(
                    query=user_message,
                    candidates=(
                        MemoryCandidate(
                            "mem_auth",
                            "Previous login fix used token expiry checks.",
                        ),
                        MemoryCandidate(
                            "mem_ui",
                            "The settings screen uses a compact layout.",
                        ),
                    ),
                    limit=1,
                ),
                token_override=tokens,
            )
            response = f"selected IDs={list(selection.selected_ids)}; tools=0"
        else:
            response = router.call(
                agent,
                user_message,
                task=task,
                token_override=tokens,
            )

        # Show truncated response
        resp_preview = response.replace("\n", "\n  │  ")[:100]
        print(f"  │  输出: {resp_preview}...")
        print(f"  │  tokens: {tokens}, cost: ${model.cost(tokens):.6f}")
        print(f"  └─ done")
        print()

    # Final cost summary
    print("─" * 60)
    print("本次对话成本明细:")
    print(router.tracker.summary())


# ═══════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════

def interactive():
    """Interactive router shell for trying agent -> model mappings."""
    print("s08: Model Routing Interactive")
    router = ModelRouter()
    selector = MemorySelectorRouter(router)
    print("Commands:")
    print("  table")
    print("  route <agent>")
    print("  auto <task>                 — README #1: route by task type")
    print("  effort [tokens]             — README #2: craft cost at low/med/high")
    print("  down <tier> / up <tier>     — README #4: mark tier unavailable / restore")
    print("  select <query>")
    print("  call <agent> [task] [prompt]")
    print("  cost")
    print("  reset")
    print("  q")
    while True:
        try:
            line = input("s08 >> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line or line.lower() in {"q", "quit", "exit"}:
            return
        if line == "table":
            router.print_routing_table()
            continue
        if line.startswith("route "):
            agent = line[6:].strip()
            model = router.route_request(agent)
            print(f"{agent} -> {model.tier.value} ({model.name})")
            continue
        if line.startswith("auto "):
            task = line[5:].strip()
            try:
                model = router.route_request("Worker", mode="auto", task=task)
            except ValueError as exc:
                print(exc)
                continue
            print(f"auto task={task} -> {model.tier.value} ({model.name})")
            continue
        if line == "effort" or line.startswith("effort "):
            raw = line[6:].strip()
            tokens = int(raw) if raw.isdigit() else 5_000
            craft = router.models[ModelTier.CRAFT]
            for effort in ("low", "medium", "high"):
                print(
                    f"  effort={effort:<6} ×{effort_cost_multiplier(effort):.1f}  "
                    f"${craft.cost(tokens, effort=effort):.6f}"
                )
            continue
        if line.startswith("down ") or line.startswith("up "):
            action, _, name = line.partition(" ")
            name = name.strip().lower()
            try:
                tier = ModelTier(name)
            except ValueError:
                print("tier must be: lite | default | craft")
                continue
            router.set_unavailable(tier, down=(action == "down"))
            dead = ",".join(t.value for t in sorted(router.unavailable, key=lambda t: t.value)) or "(none)"
            print(f"unavailable={dead}")
            continue
        if line.startswith("select "):
            query = line[7:].strip()
            result = selector.select(
                MemorySelectionRequest(
                    query=query,
                    candidates=(
                        MemoryCandidate("mem_auth", "Login token expiry decision."),
                        MemoryCandidate("mem_ui", "Compact settings layout preference."),
                        MemoryCandidate("mem_ci", "CI runs the offline verification suite."),
                    ),
                    limit=2,
                )
            )
            print(
                f"[{result.route.model.tier.value}; tools=0] "
                f"selected={list(result.selected_ids)}"
            )
            continue
        if line.startswith("call "):
            parts = line.split(" ", 3)
            agent = parts[1] if len(parts) > 1 else "CLI"
            task = parts[2] if len(parts) > 2 else ""
            prompt = parts[3] if len(parts) > 3 else "demo prompt"
            try:
                response = router.call(agent, prompt, task=task)
            except ValueError as exc:
                print(exc)
                continue
            model = router.route_request(agent)
            print(f"[{model.tier.value}] {response}")
            continue
        if line == "cost":
            print(router.tracker.summary())
            continue
        if line == "reset":
            router.tracker.reset()
            print("cost tracker reset")
            continue
        print(
            "Unknown command. Use: table | route <agent> | auto <task> | "
            "effort [tokens] | down/up <tier> | select <query> | "
            "call <agent> [task] [prompt] | cost | reset | q"
        )


def main():
    print("╔═══════════════════════════════════════════════════════════╗")
    print("║  s08: Model Routing — 用 AI 管理 AI                       ║")
    print("║  便宜的做粗筛, 贵的做推理                                  ║")
    print("╚═══════════════════════════════════════════════════════════╝")

    router = ModelRouter()

    # Show routing table
    router.print_routing_table()

    # Show model matrix
    print("\n模型矩阵:")
    print(f"  {'Tier':<12} {'Model':<30} {'Cost/M':<10} {'Latency':<10} "
          f"{'Context':<10} {'Features'}")
    print(f"  {'─'*12} {'─'*30} {'─'*10} {'─'*10} {'─'*10} {'─'*20}")
    for tier in [ModelTier.LITE, ModelTier.DEFAULT, ModelTier.CRAFT]:
        m = router.models[tier]
        print(f"  {tier.value:<12} {m.name:<30} ${m.cost_per_million:<9} "
              f"{m.latency_ms}ms{'':<5} {m.context_window//1000}K{'':<7} "
              f"{','.join(m.features)}")

    # Run all demos
    demo_use_ai_to_manage_ai(router)
    demo_auto_routing(router)
    demo_effort(router)
    demo_fallback(router)
    demo_cost_comparison(router)
    demo_agent_loop(router)

    print("\n" + "=" * 60)
    print("核心要点:")
    print("  1. 不是所有任务都用最贵的模型")
    print("  2. lite 模型做粗筛/分类, craft 模型做推理/交互")
    print("  3. memory selector 只选已有候选 ID, 不加载或执行工具")
    print("  4. '用 AI 管理 AI' = 便宜的先过滤, 贵的只看结果")
    print("  5. 成本可降低 50-90%, 上下文质量反而更好")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Model routing demo")
    parser.add_argument("--interactive", action="store_true", help="open an interactive model routing shell")
    args = parser.parse_args()
    if args.interactive:
        interactive()
    else:
        main()
