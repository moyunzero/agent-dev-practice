"""Shared chapter demo helpers.

The 24 lesson files are intentionally small, standalone scripts. This
module gives them a common learning entrypoint without moving their core
code into a framework:

    python s01_agent_loop/code.py --demo
    python s01_agent_loop/code.py --provider deepseek

`--demo` is offline and keyless. `--provider deepseek` maps DeepSeek's
Anthropic-compatible API into the environment variables the earlier
chapters already understand.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any


def _load_env(*, override: bool = True) -> None:
    try:
        from dotenv import load_dotenv
    except Exception:
        return
    load_dotenv(override=override)


def _apply_deepseek_env() -> None:
    key = os.getenv("DEEPSEEK_API_KEY")
    if key:
        os.environ["ANTHROPIC_API_KEY"] = key
    os.environ["ANTHROPIC_BASE_URL"] = os.getenv(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com/anthropic",
    )
    os.environ["MODEL_ID"] = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
    os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)


def _patch_dotenv_for_provider(provider: str) -> None:
    """Keep later chapter-local load_dotenv calls from undoing provider mapping."""
    if provider != "deepseek":
        return
    try:
        import dotenv
    except Exception:
        return
    original = dotenv.load_dotenv

    def patched_load_dotenv(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        _apply_deepseek_env()
        return result

    dotenv.load_dotenv = patched_load_dotenv


def _take_provider_arg(argv: list[str]) -> str | None:
    provider: str | None = None
    cleaned: list[str] = [argv[0]]
    i = 1
    while i < len(argv):
        item = argv[i]
        if item == "--provider":
            if i + 1 >= len(argv):
                raise SystemExit("--provider requires: anthropic | deepseek")
            provider = argv[i + 1]
            i += 2
            continue
        if item.startswith("--provider="):
            provider = item.split("=", 1)[1]
            i += 1
            continue
        cleaned.append(item)
        i += 1
    argv[:] = cleaned
    return provider


def prepare_chapter_provider() -> str:
    """Normalize provider flags for API-backed lesson scripts.

    Most lesson chapters were written against the Anthropic Messages API.
    DeepSeek's Anthropic-compatible endpoint lets readers use the same
    teaching code with only a DeepSeek key. This helper converts:

        --provider deepseek

    into the environment expected by those chapters, then removes the
    provider flag so chapter-specific argparse code remains simple.
    """

    _load_env()
    provider = (_take_provider_arg(sys.argv) or os.getenv("PROVIDER") or "anthropic").lower()
    if provider == "deepseek":
        _apply_deepseek_env()
        _patch_dotenv_for_provider(provider)
    elif provider == "anthropic":
        if os.getenv("ANTHROPIC_BASE_URL"):
            os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    else:
        raise SystemExit("Lesson provider must be anthropic or deepseek.")
    return provider


def maybe_run_chapter_demo(file: str, progression: dict[str, Any]) -> None:
    """Run shared chapter entrypoints before chapter-specific code loads.

    - `--demo` is offline and keyless.
    - `--eval` is a real-provider benchmark path used by every chapter.
      It is deliberately intercepted before the chapter imports Anthropic
      directly, so even mock-only chapters can be evaluated online.
    """

    if "--eval" in sys.argv:
        run_chapter_eval(file, progression)
        raise SystemExit(0)
    if "--demo" not in sys.argv:
        return
    sys.argv[:] = [arg for arg in sys.argv if arg != "--demo"]
    run_chapter_demo(file, progression)
    raise SystemExit(0)


def _eval_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a model-backed chapter evaluation.")
    parser.add_argument("--eval", action="store_true")
    parser.add_argument(
        "--provider",
        choices=["anthropic", "deepseek", "openai", "openai-chat", "offline"],
        default=None,
    )
    parser.add_argument("--prompt", default=None)
    parser.add_argument("--max-turns", type=int, default=5)
    parser.add_argument("--trace", default=None, help="JSONL trace output path")
    args, _unknown = parser.parse_known_args(sys.argv[1:])
    return args


def _tool_argument(tool_name: str, tool_input: dict[str, Any]) -> str:
    if tool_name == "bash":
        return str(tool_input.get("command", ""))
    if tool_name == "read_file":
        return str(tool_input.get("path", ""))
    if tool_name == "tool_search":
        return str(tool_input.get("query", ""))
    raise KeyError(f"unknown tool: {tool_name}")


def _append_trace(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {"timestamp": int(time.time() * 1000), **event}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(envelope, ensure_ascii=False) + "\n")


def _default_eval_prompt(progression: dict[str, Any]) -> str:
    chapter = progression.get("chapter", "chapter")
    adds = ", ".join(progression.get("adds") or [])
    return (
        f"You are evaluating {chapter} in learn-workbuddy. "
        "Use the available tools through the harness. First call tool_search, "
        "then run pwd, then read this chapter's README.md if possible. "
        f"Explain in two bullets how this chapter teaches: {adds}. "
        "End your final answer with DONE."
    )


def run_chapter_eval(file: str, progression: dict[str, Any]) -> None:
    """Run one chapter through the shared provider adapter and emit a trace.

    This is the online-evaluable counterpart to each chapter's interactive
    CLI. The benchmark calls this path for every `sXX/code.py` so the eval
    artifact contains the actual model/tool trajectory, not just stdout.
    """

    args = _eval_parser()
    _load_env()
    from dotenv import load_dotenv

    load_dotenv(override=True)

    root = Path(file).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    os.environ.setdefault(
        "MINI_WORKBUDDY_HOME",
        str(root / ".workbuddy_eval" / str(progression.get("chapter", Path(file).resolve().parent.name))),
    )

    from mini_workbuddy.audit import AuditLog
    from mini_workbuddy.config import HarnessConfig
    from mini_workbuddy.events import EventBus
    from mini_workbuddy.providers import (
        ProviderRequest,
        append_provider_message,
        normalized_tools,
        select_provider,
    )
    from mini_workbuddy.storage import Storage
    from mini_workbuddy.tools import ToolRegistry

    provider = select_provider(args.provider)
    config = HarnessConfig.from_env()
    storage = Storage(config)
    events = EventBus()
    audit = AuditLog(config)
    tools = ToolRegistry(config, storage)

    chapter_path = Path(file).resolve()
    chapter_dir = chapter_path.parent
    session = storage.create_session(
        cwd=str(chapter_dir),
        title=f"benchmark eval {progression.get('chapter', chapter_dir.name)}",
    )
    prompt = args.prompt or _default_eval_prompt(progression)
    trace_path = Path(args.trace).expanduser() if args.trace else (
        config.root_dir / "eval-traces" / f"{progression.get('chapter', chapter_dir.name)}.jsonl"
    )
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text("", encoding="utf-8")

    system = (
        f"You are running a model-backed benchmark for {progression.get('chapter', chapter_dir.name)}. "
        f"Workspace: {session.cwd}. "
        "Use tools to gather evidence. Prefer safe read-only commands. "
        "You must call at least one tool before finalizing."
    )
    messages: list[Any] = [provider.initial_user_message(prompt)]

    storage.append_event(session, {"type": "message", "role": "user", "content": prompt})
    audit.append("eval_user_prompt", {"sessionId": session.id, "chapter": progression.get("chapter"), "provider": provider.name})
    _append_trace(trace_path, {
        "type": "case_start",
        "chapter": progression.get("chapter"),
        "provider": provider.name,
        "model": provider.model,
        "prompt": prompt,
        "session": session.id,
    })

    print(f"Eval chapter: {progression.get('chapter', chapter_dir.name)}")
    print(f"Provider: {provider.name}")
    print(f"Model: {provider.model}")
    print(f"Session: {session.id}")
    print(f"Trace: {trace_path}")

    final_text = ""
    tool_count = 0
    for turn in range(1, args.max_turns + 1):
        _append_trace(trace_path, {"type": "model_request", "turn": turn, "messages": len(messages)})
        model_turn = provider.create(
            ProviderRequest(
                system=system,
                messages=messages,
                tools=normalized_tools(),
                max_tokens=2000,
                required_tool="tool_search" if turn == 1 else None,
            )
        )
        append_provider_message(messages, model_turn.raw_assistant)
        _append_trace(trace_path, {
            "type": "model_response",
            "turn": turn,
            "text": model_turn.text,
            "tool_calls": [asdict(call) for call in model_turn.tool_calls],
        })

        if model_turn.text:
            final_text = model_turn.text
            print(model_turn.text)

        if not model_turn.wants_tools:
            storage.append_event(session, {"type": "message", "role": "assistant", "content": final_text})
            audit.append("eval_assistant_message", {"sessionId": session.id, "content": final_text[:500]})
            break

        results = []
        for call in model_turn.tool_calls:
            argument = _tool_argument(call.name, call.arguments)
            tool_count += 1
            _append_trace(trace_path, {
                "type": "tool_call",
                "turn": turn,
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            })
            audit.append("eval_tool_call", {"sessionId": session.id, "tool": call.name, "argument": argument})
            try:
                result = tools.run(call.name, argument, session)
                storage.append_event(session, {"type": "tool_result", **asdict(result)})
                events.publish("session_update", {"sessionId": session.id, "type": "tool_result", **asdict(result)})
                output = result.content
                audit.append("eval_tool_result", {
                    "sessionId": session.id,
                    "tool": result.name,
                    "externalized": result.externalized_path is not None,
                    "exit_code": result.exit_code,
                })
                _append_trace(trace_path, {
                    "type": "tool_result",
                    "turn": turn,
                    "id": call.id,
                    "name": result.name,
                    "exit_code": result.exit_code,
                    "externalized_path": result.externalized_path,
                    "content_preview": result.content[:1000],
                })
            except Exception as exc:
                output = f"Tool failed: {exc}"
                audit.append("eval_tool_error", {"sessionId": session.id, "tool": call.name, "error": str(exc)})
                _append_trace(trace_path, {
                    "type": "tool_error",
                    "turn": turn,
                    "id": call.id,
                    "name": call.name,
                    "error": str(exc),
                })
            print(f"[tool_call] {call.name}: {argument}")
            print(output[:500])
            results.append((call, output))

        append_provider_message(messages, provider.format_tool_results(results))
    else:
        _append_trace(trace_path, {"type": "max_turns", "max_turns": args.max_turns})

    transcript = storage.read_transcript(session)
    audit_ok = audit.verify()
    _append_trace(trace_path, {
        "type": "case_end",
        "chapter": progression.get("chapter"),
        "provider": provider.name,
        "tool_calls": tool_count,
        "transcript_events": len(transcript),
        "audit_verified": audit_ok,
        "done": "DONE" in final_text.upper(),
    })

    print("Transcript:", storage.transcript_path(session))
    print("Transcript events:", len(transcript))
    print("Audit file:", audit.path)
    print("Audit verified:", audit_ok)
    print("Tool calls:", tool_count)
    print("RESULT:", "OK" if tool_count > 0 and audit_ok else "FAIL")


def run_chapter_demo(file: str, progression: dict[str, Any]) -> None:
    path = Path(file).resolve()
    chapter_dir = path.parent
    readme = chapter_dir / "README.md"
    title = chapter_dir.name
    if readme.exists():
        first = readme.read_text(encoding="utf-8", errors="ignore").splitlines()
        if first:
            title = first[0].lstrip("# ").strip()

    print(f"{title}")
    print("=" * len(title))
    print()
    print("这是离线学习 demo：不调用模型、不需要 API key，只说明本章在渐进链路中的位置。")
    print("要体验真实模型交互，配置 .env 后直接运行本章脚本。")
    print()

    builds_on = progression.get("builds_on") or []
    adds = progression.get("adds") or []
    preserves = progression.get("preserves") or []

    print("继承自:")
    print("  " + (", ".join(builds_on) if builds_on else "无，这是最小起点"))
    print()
    print("本章新增:")
    for item in adds:
        print(f"  - {item}")
    print()
    print("继续保留:")
    for item in preserves:
        print(f"  - {item}")

    if readme.exists():
        text = readme.read_text(encoding="utf-8", errors="ignore")
        has_arch = "## 代码架构图" in text and "```mermaid" in text
        has_image = "![" in text
        print()
        print("学习材料:")
        print(f"  - README: {readme.relative_to(path.parents[1])}")
        print(f"  - 代码架构图: {'有' if has_arch else '缺失'}")
        print(f"  - 配图: {'有' if has_image else '缺失'}")

    rel = path.relative_to(path.parents[1]).as_posix()
    print()
    print("在线体验:")
    print("  cp .env.example .env")
    print("  # 填 DEEPSEEK_API_KEY 后：")
    print(f"  python3 {rel} --provider deepseek")
    print()
    print("本章 demo 完成。")
