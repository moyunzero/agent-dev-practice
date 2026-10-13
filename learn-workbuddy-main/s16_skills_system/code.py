#!/usr/bin/env python3
from __future__ import annotations
"""
s16_skills_system.py - Skills System: SKILL.md Frontmatter + On-Demand Loading

Skills are stored in two levels:
  - User-level: ~/.workbuddy/skills/ (personal, cross-project)
  - Project-level: {workspace}/.workbuddy/skills/ (project-specific, shared)

Each skill is a directory with a SKILL.md file.
SKILL.md has YAML frontmatter: title, summary, read_when (triggers), and a
strict permissions manifest for tools, network, and workspace-relative paths.

Loading is on-demand:
  1. Startup: scan frontmatter → build index (no full content loaded)
  2. User input: match against read_when triggers
  3. Match found: load full SKILL.md content into context
  4. System prompt reassembled (s15)

  ┌───────────────────────────────────────────────────┐
  │              Skills Lifecycle                      │
  │                                                   │
  │  Startup:                                         │
  │    scan SKILL.md files → parse frontmatter only   │
  │    build index: [{title, summary, read_when}]      │
  │    inject index into system prompt (~50 tok each)  │
  │                                                   │
  │  User input: "帮我提交代码"                          │
  │    match "提交" → git-commit skill                  │
  │    load SKILL.md full content                      │
  │    reassemble system prompt                        │
  │    agent now has commit guidelines                 │
  │                                                   │
  │  Agent can also call Skill tool to load manually   │
  │  Agent can create new skills after tasks           │
  └───────────────────────────────────────────────────┘

Production harnesses often use: same frontmatter + on-demand model in agent bridge,
with install audit, permission diff, runtime policy, and sandbox enforcement.
Teaching version uses: in-memory skills, keyword matching.

Usage:
    python s16_skills_system/code.py
"""



# Machine-readable learning path metadata. Tests enforce that every
# chapter declares what it inherits and what it adds.
PROGRESSION = {'chapter': 's16_skills_system',
 'builds_on': ['s15_prompt_assembly'],
 'adds': ['SKILL.md discovery', 'frontmatter parsing', 'on-demand skill loading',
          'declarative skill permissions'],
 'preserves': ['prompt assembly pipeline', 'harness permission ceiling']}

# Shared learning entrypoints: --demo is offline; --provider deepseek configures real API env.
import sys as _wb_sys
from pathlib import Path as _wb_Path
_WB_ROOT = _wb_Path(__file__).resolve().parents[1]
if str(_WB_ROOT) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_WB_ROOT))
from mini_workbuddy.chapter_demo import maybe_run_chapter_demo as _wb_maybe_run_chapter_demo
_wb_maybe_run_chapter_demo(__file__, PROGRESSION)
from mini_workbuddy.chapter_demo import prepare_chapter_provider as _wb_prepare_chapter_provider
_wb_prepare_chapter_provider()
import fnmatch, os, re, sys, time, json
from pathlib import Path
from dataclasses import dataclass, field

try:
    import readline
    readline.parse_and_bind('set bind-tty-special-chars off')
    readline.parse_and_bind('set input-meta on')
    readline.parse_and_bind('set output-meta on')
    readline.parse_and_bind('set convert-meta off')
except ImportError:
    pass

from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(override=True)
if os.getenv("ANTHROPIC_BASE_URL"): os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)

WORKDIR = Path.cwd()
client = Anthropic(base_url=os.getenv("ANTHROPIC_BASE_URL"))
MODEL = os.environ.get("MODEL_ID")
if not MODEL:
    raise SystemExit(
        "MODEL_ID is not set. Copy .env.example to .env and fill in "
        "ANTHROPIC_API_KEY and MODEL_ID (see README quick start)."
    )

try:
    import yaml
except ImportError:
    yaml = None


# ======================================================================
# Declarative skill permissions
# ======================================================================

class SkillPermissionError(ValueError):
    """Raised when a skill permission manifest is malformed."""


@dataclass(frozen=True)
class SkillPermissions:
    """Capabilities requested by one skill.

    This manifest can only narrow the harness policy. Declaring a capability
    never grants authority that the underlying permission layer denied.
    """

    tools: tuple[str, ...] = ()
    network: bool = False
    read_paths: tuple[str, ...] = ()
    write_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "tools": list(self.tools),
            "network": self.network,
            "paths": {
                "read": list(self.read_paths),
                "write": list(self.write_paths),
            },
        }


_TOOL_NAME = re.compile(r"^[A-Za-z0-9_.:-]+$")
_NETWORK_COMMAND_PATTERNS = (
    "curl ", "wget ", "git clone", "npm install", "pip install",
)


def _unique_strings(value, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise SkillPermissionError(f"permissions.{field_name} must be a list")
    result = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SkillPermissionError(
                f"permissions.{field_name} entries must be non-empty strings"
            )
        item = item.strip()
        if item not in result:
            result.append(item)
    return tuple(result)


def _validate_path_pattern(pattern: str, *, field_name: str) -> str:
    normalized = pattern.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith("/"):
        raise SkillPermissionError(
            f"permissions.paths.{field_name} must stay relative to the workspace"
        )
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise SkillPermissionError(
            f"permissions.paths.{field_name} must not escape the workspace"
        )
    return "/".join(parts)


def parse_skill_permissions(value) -> SkillPermissions:
    """Parse a strict, fail-closed permissions block from frontmatter."""
    if value is None:
        return SkillPermissions()
    if not isinstance(value, dict):
        raise SkillPermissionError("permissions must be a mapping")

    unknown = set(value) - {"tools", "network", "paths"}
    if unknown:
        raise SkillPermissionError(
            f"unknown permissions fields: {', '.join(sorted(unknown))}"
        )

    tools = _unique_strings(value.get("tools", []), field_name="tools")
    for tool in tools:
        if not _TOOL_NAME.fullmatch(tool):
            raise SkillPermissionError(f"invalid tool name in permissions.tools: {tool}")

    network = value.get("network", False)
    if not isinstance(network, bool):
        raise SkillPermissionError("permissions.network must be true or false")

    paths = value.get("paths", {})
    if not isinstance(paths, dict):
        raise SkillPermissionError("permissions.paths must be a mapping")
    unknown_paths = set(paths) - {"read", "write"}
    if unknown_paths:
        raise SkillPermissionError(
            f"unknown permissions.paths fields: {', '.join(sorted(unknown_paths))}"
        )

    read_paths = tuple(
        _validate_path_pattern(pattern, field_name="read")
        for pattern in _unique_strings(paths.get("read", []), field_name="paths.read")
    )
    write_paths = tuple(
        _validate_path_pattern(pattern, field_name="write")
        for pattern in _unique_strings(paths.get("write", []), field_name="paths.write")
    )
    return SkillPermissions(tools, network, read_paths, write_paths)


def permission_diff(
    previous: SkillPermissions, requested: SkillPermissions
) -> dict[str, object]:
    """Return only permission additions so updates can surface escalation."""
    return {
        "added_tools": sorted(set(requested.tools) - set(previous.tools)),
        "network_enabled": requested.network and not previous.network,
        "added_read_paths": sorted(
            set(requested.read_paths) - set(previous.read_paths)
        ),
        "added_write_paths": sorted(
            set(requested.write_paths) - set(previous.write_paths)
        ),
    }


def has_permission_escalation(diff: dict[str, object]) -> bool:
    return any(bool(value) for value in diff.values())


def _path_is_allowed(path: str, patterns: tuple[str, ...], workdir: Path) -> bool:
    try:
        resolved = (workdir / path).resolve()
        relative = resolved.relative_to(workdir.resolve()).as_posix()
    except (OSError, ValueError):
        return False
    return any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns)


def authorize_skill_tool(
    skill: "Skill", tool_name: str, tool_input: dict, *, workdir: Path | None = None
) -> tuple[bool, str]:
    """Check one skill manifest before the harness executes a tool call."""
    if tool_name not in skill.permissions.tools:
        return False, f"skill '{skill.title}' did not declare tool '{tool_name}'"

    command = str(tool_input.get("command", "")).lower()
    if tool_name == "bash" and any(
        pattern in command for pattern in _NETWORK_COMMAND_PATTERNS
    ) and not skill.permissions.network:
        return False, f"skill '{skill.title}' did not declare network access"

    path = tool_input.get("path")
    if isinstance(path, str) and tool_name == "read_file":
        root = workdir or WORKDIR
        if not _path_is_allowed(path, skill.permissions.read_paths, root):
            return False, f"skill '{skill.title}' cannot read path '{path}'"
    if isinstance(path, str) and tool_name == "write_file":
        root = workdir or WORKDIR
        if not _path_is_allowed(path, skill.permissions.write_paths, root):
            return False, f"skill '{skill.title}' cannot write path '{path}'"

    return True, "allowed by skill manifest; harness policy still applies"


# ======================================================================
# SKILL.md parsing
# ======================================================================

@dataclass
class Skill:
    """A skill parsed from SKILL.md."""
    title: str
    summary: str
    read_when: list[str]
    path: str
    content: str = ""           # Full content (loaded on demand)
    loaded: bool = False        # Whether full content is in context
    agent_created: bool = False
    permissions: SkillPermissions = field(default_factory=SkillPermissions)

    def index_line(self) -> str:
        """One-line index entry for system prompt (compact)."""
        return f"- **{self.title}**: {self.summary}"

    def full_block(self) -> str:
        """Full content block for system prompt (when loaded)."""
        return f"## 技能: {self.title}\n{self.content}"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown text.

    Returns: (frontmatter_dict, body_text)
    """
    if not text.startswith("---"):
        return {}, text

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text

    if yaml:
        fm = yaml.safe_load(parts[1]) or {}
        if not isinstance(fm, dict):
            raise SkillPermissionError("frontmatter must be a mapping")
    else:
        # Fallback: simple parsing without yaml
        fm = {}
        for line in parts[1].strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                fm[key.strip()] = val.strip()

    return fm, parts[2].strip()


def parse_skill_md(filepath: Path) -> Skill | None:
    """Parse a SKILL.md file into a Skill object."""
    try:
        text = filepath.read_text()
    except Exception:
        return None

    fm, body = parse_frontmatter(text)

    return Skill(
        title=fm.get("title", filepath.parent.name),
        summary=fm.get("summary", ""),
        read_when=fm.get("read_when", []) if isinstance(fm.get("read_when"), list)
                   else [fm.get("read_when", "")],
        path=str(filepath),
        content=body,
        loaded=False,
        agent_created=fm.get("agent_created", False),
        permissions=parse_skill_permissions(fm.get("permissions")),
    )


# ======================================================================
# Pre-seeded skills (simulating SKILL.md files)
# ======================================================================

# In real WorkBuddy, these live as actual SKILL.md files in
# ~/.workbuddy/skills/ and {workspace}/.workbuddy/skills/
# Teaching version: we seed them in memory.

SEED_SKILLS = {
    "git-commit": '''---
title: git-commit
summary: 规范的 git 提交流程
read_when:
  - 提交代码
  - commit
  - git push
  - 保存修改
agent_created: false
permissions:
  tools: [bash]
  network: false
  paths:
    read: ["**"]
    write: []
---

# Git Commit 技能

## 步骤
1. 运行 `git status` 查看变更
2. 运行 `git diff` 检查改动内容
3. 暂存相关文件: `git add <files>`
4. 生成规范的 commit message:
   - 格式: `type(scope): description`
   - type: feat/fix/docs/refactor/test/chore
   - description 用中文, 不超过 50 字
5. 提交: `git commit -m "type(scope): description"`

## 注意事项
- 不要提交 .env 等敏感文件
- 一个 commit 只做一件事
- commit message 要描述"做了什么", 不是"改了哪个文件"''',

    "code-review": '''---
title: code-review
summary: 代码审查流程和检查清单
read_when:
  - 代码审查
  - code review
  - review
  - 审查代码
agent_created: false
permissions:
  tools: [read_file]
  network: false
  paths:
    read: ["**"]
    write: []
---

# Code Review 技能

## 审查步骤
1. 先理解改动目的 (读 commit message 和 PR 描述)
2. 检查逻辑正确性
3. 检查错误处理
4. 检查命名和可读性
5. 检查测试覆盖

## 检查清单
- [ ] 是否有硬编码的密钥/密码?
- [ ] 是否有 SQL 注入风险?
- [ ] 是否有未处理的异常?
- [ ] 命名是否清晰表达意图?
- [ ] 是否有重复代码?
- [ ] 测试是否覆盖关键路径?''',

    "deploy-check": '''---
title: deploy-check
summary: 部署前检查清单
read_when:
  - 部署
  - deploy
  - 上线
  - 发布
agent_created: false
permissions:
  tools: [bash]
  network: false
  paths:
    read: ["**"]
    write: []
---

# Deploy Check 技能

## 部署前检查
1. 所有测试通过: `npm test` / `pytest`
2. 代码已提交并推送: `git status` (clean)
3. 版本号已更新
4. 环境变量已配置
5. 数据库迁移已准备
6. 回滚方案已确认

## 部署后验证
1. 健康检查通过
2. 关键功能冒烟测试
3. 监控指标正常
4. 日志无异常''',
}


def build_skill_index() -> list[Skill]:
    """Build skill index from seed data.

    In real WorkBuddy:
    - Scan ~/.workbuddy/skills/*/SKILL.md (user-level)
    - Scan {workspace}/.workbuddy/skills/*/SKILL.md (project-level)
    - Parse frontmatter only, don't load full content
    - Project-level skills take priority

    Teaching version: seed from SEED_SKILLS dict.
    """
    skills = []
    for name, content in SEED_SKILLS.items():
        fm, body = parse_frontmatter(content)
        skill = Skill(
            title=fm.get("title", name),
            summary=fm.get("summary", ""),
            read_when=fm.get("read_when", []),
            path=f"(memory)/{name}/SKILL.md",
            content=body,
            loaded=False,
            agent_created=fm.get("agent_created", False),
            permissions=parse_skill_permissions(fm.get("permissions")),
        )
        skills.append(skill)
    return skills


# ======================================================================
# Skill management
# ======================================================================

skill_index: list[Skill] = build_skill_index()
loaded_skills: list[Skill] = []


def match_skill(user_input: str) -> str | None:
    """Check if user input matches any skill's trigger keywords.

    Production harness: may use semantic matching (embeddings).
    Teaching version: simple keyword inclusion.
    """
    input_lower = user_input.lower()

    for skill in skill_index:
        for trigger in skill.read_when:
            if trigger.lower() in input_lower:
                return skill.title

    return None


def load_skill(title: str) -> str:
    """Load a skill's full content into context.

    1. Find skill in index
    2. Mark as loaded
    3. Add to loaded_skills list
    4. Return loaded content
    """
    for skill in skill_index:
        if skill.title == title:
            if skill.loaded:
                return f"技能 '{title}' 已在上下文中。"
            skill.loaded = True
            loaded_skills.append(skill)
            return f"技能 '{title}' 已加载。内容:\n{skill.content}"
    return f"未找到技能 '{title}'。可用: {[s.title for s in skill_index]}"


def create_skill(title: str, summary: str, read_when: list[str],
                 content: str, permissions: dict | None = None) -> str:
    """Create a new skill.

    In real WorkBuddy, this writes to ~/.workbuddy/skills/{title}/SKILL.md
    with agent_created: true in frontmatter.
    """
    # Check if already exists
    existing = [s for s in skill_index if s.title == title]
    if existing:
        return f"技能 '{title}' 已存在。"

    requested_permissions = parse_skill_permissions(permissions)

    # Build SKILL.md content
    triggers_yaml = "\n".join(f"  - {t}" for t in read_when)
    permissions_yaml = json.dumps(
        requested_permissions.as_dict(), ensure_ascii=False
    )
    skill_md = f"""---
title: {title}
summary: {summary}
read_when:
{triggers_yaml}
agent_created: true
permissions: {permissions_yaml}
---

{content}"""

    fm, body = parse_frontmatter(skill_md)
    new_skill = Skill(
        title=title,
        summary=summary,
        read_when=read_when,
        path=f"(memory)/{title}/SKILL.md",
        content=body,
        loaded=False,
        agent_created=True,
        permissions=requested_permissions,
    )
    skill_index.append(new_skill)
    SEED_SKILLS[title] = skill_md  # Keep in sync

    return f"技能 '{title}' 已创建。"


def audit_skill(
    skill_content: str,
    previous_permissions: SkillPermissions | None = None,
) -> tuple[str, str]:
    """Security audit a skill before installing.

    P0: Dangerous patterns — block installation
    P1: Network/install operations — require user approval
    P2: Safe — allow installation

    Production harness: more sophisticated AST analysis.
    Teaching version: pattern matching.
    """
    try:
        frontmatter, _ = parse_frontmatter(skill_content)
        requested_permissions = parse_skill_permissions(
            frontmatter.get("permissions")
        )
    except SkillPermissionError as exc:
        return ("P0", f"禁止安装: 权限声明无效 ({exc})")

    p0_patterns = [
        ("rm -rf /", "递归删除根目录"),
        ("sudo ", "提权操作"),
        ("eval(", "动态代码执行"),
        ("exec(", "动态代码执行"),
        ("os.system(", "系统命令执行"),
        ("__import__", "动态导入"),
    ]

    p1_patterns = [
        ("curl ", "网络请求"),
        ("wget ", "网络下载"),
        ("npm install", "包安装"),
        ("pip install", "包安装"),
        ("git clone", "代码克隆"),
        ("chmod 777", "过度权限"),
    ]

    for pattern, desc in p0_patterns:
        if pattern in skill_content:
            return ("P0", f"禁止安装: 包含危险模式 '{pattern}' ({desc})")

    for pattern, desc in p1_patterns:
        if pattern in skill_content:
            return ("P1", f"需审批: 包含 '{pattern}' ({desc})")

    if previous_permissions is not None:
        diff = permission_diff(previous_permissions, requested_permissions)
        if has_permission_escalation(diff):
            return (
                "P1",
                "需审批: Skill 更新扩大权限 "
                + json.dumps(diff, ensure_ascii=False, sort_keys=True),
            )

    if requested_permissions.network or requested_permissions.write_paths:
        return ("P1", "需审批: Skill 请求网络访问或写路径权限")

    return ("P2", "安全: 未检测到危险模式")


# ======================================================================
# System prompt with skill index
# ======================================================================

def build_system_prompt() -> str:
    """Build system prompt with skill index (not full content).

    The index only shows title + summary — ~50 tokens per skill.
    Full content is loaded on demand.
    """
    base = f"""你是一个桌面 AI 助手, 工作目录: {WORKDIR}

你有以下技能可用。当用户需求匹配时, 调用 Skill 工具加载完整内容:

{chr(10).join(s.index_line() for s in skill_index)}

当技能匹配时, 主动调用 Skill 工具加载。"""

    # Add loaded skills' full content
    if loaded_skills:
        loaded_blocks = "\n\n".join(s.full_block() for s in loaded_skills)
        base += f"\n\n---\n\n{loaded_blocks}"

    return base


# ======================================================================
# Tools
# ======================================================================

def run_skill(skill: str) -> str:
    """Skill tool — load a skill by name."""
    return load_skill(skill)

def run_bash(command: str) -> str:
    import subprocess
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()[:3000] or "(no output)"
    except Exception as e:
        return f"Error: {e}"

def run_read(path: str) -> str:
    try:
        p = (WORKDIR / path).resolve()
        if not p.is_relative_to(WORKDIR):
            return "Error: path escapes workspace"
        return p.read_text()[:3000]
    except Exception as e:
        return f"Error: {e}"


TOOLS = [
    {
        "name": "Skill",
        "description": "Load a skill by name. Use this when the user's request matches a skill's trigger. Available skills: " + ", ".join(s.title for s in skill_index),
        "input_schema": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "description": "The skill name to load",
                },
            },
            "required": ["skill"],
        },
    },
    {
        "name": "bash",
        "description": "Run a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
        },
    },
    {
        "name": "read_file",
        "description": "Read file contents.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
]

TOOL_HANDLERS = {"Skill": run_skill, "bash": run_bash, "read_file": run_read}


def authorize_loaded_skill_tool(
    tool_name: str, tool_input: dict, *, workdir: Path | None = None
) -> tuple[bool, str]:
    """Apply active Skill overlays without replacing the base harness policy.

    With no active skill, s04-style harness permissions remain authoritative.
    When skills are active, at least one reviewed manifest must declare the
    capability. A production dispatcher should also bind each call to its
    originating skill instead of using this teaching union.
    """
    if tool_name == "Skill" or not loaded_skills:
        return True, "base harness policy applies"

    reasons = []
    for skill in loaded_skills:
        allowed, reason = authorize_skill_tool(
            skill, tool_name, tool_input, workdir=workdir
        )
        if allowed:
            return True, reason
        reasons.append(reason)
    return False, "; ".join(reasons)


# ======================================================================
# Agent Loop
# ======================================================================

def agent_loop(messages: list):
    """Agent loop with skill auto-matching and on-demand loading."""
    while True:
        # Rebuild system prompt (may include newly loaded skills)
        system = build_system_prompt()

        response = client.messages.create(
            model=MODEL, system=system, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return

        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_input = dict(block.input) if block.input else {}
            allowed, reason = authorize_loaded_skill_tool(block.name, tool_input)
            handler = TOOL_HANDLERS.get(block.name)
            if not allowed:
                output = f"Permission denied: {reason}"
            else:
                output = handler(**tool_input) if handler else f"Unknown: {block.name}"

            # Special display for Skill tool
            if block.name == "Skill":
                print(f"  \033[35m> [技能加载] {block.input.get('skill', '?')}\033[0m")
            else:
                display = str(output)[:100].replace('\n', ' ')
                print(f"  \033[36m> {block.name}\033[0m {display}")

            results.append({"type": "tool_result",
                            "tool_use_id": block.id, "content": output})

        messages.append({"role": "user", "content": results})


# ======================================================================
# Main
# ======================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("s16: Skills System — SKILL.md frontmatter, 按需加载")
    print("=" * 60)

    # Show skill index
    print(f"\n\033[90m技能索引 ({len(skill_index)} 个技能, 只加载了 frontmatter):\033[0m")
    for skill in skill_index:
        triggers = ", ".join(skill.read_when)
        loaded = "✓ 已加载" if skill.loaded else "○ 仅索引"
        print(f"\033[90m  {skill.title:<15} {loaded} | 触发词: {triggers}\033[0m")

    print(f"\n\033[90m命令:\033[0m")
    print(f"\033[90m  skills  — 列出所有技能\033[0m")
    print(f"\033[90m  load X  — 手动加载技能 X\033[0m")
    print(f"\033[90m  create  — 创建新技能\033[0m")
    print(f"\033[90m  audit   — 安全审计演示\033[0m")
    print(f"\033[90m  stats   — 查看统计\033[0m")
    print(f"\033[90m试试说 \"帮我提交代码\" — 会自动匹配 git-commit 技能\033[0m\n")

    history = []
    while True:
        try:
            query = input("\033[36ms16 >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
        if query.strip().lower() in ("q", "exit"):
            break

        cmd = query.strip().lower()

        if cmd == "skills":
            print(f"\n{'技能名':<15} {'状态':>8} {'触发词':<30} {'来源':<10}")
            print("─" * 65)
            for skill in skill_index:
                status = "已加载" if skill.loaded else "仅索引"
                triggers = ", ".join(skill.read_when)
                source = "agent" if skill.agent_created else "manual"
                print(f"{skill.title:<15} {status:>8} {triggers:<30} {source:<10}")
            continue

        if cmd.startswith("load "):
            name = query.strip().split(" ", 1)[1]
            result = load_skill(name)
            print(f"\033{result}\033[0m")
            continue

        if cmd == "create":
            # Interactive skill creation (simplified)
            print("\033[90m创建新技能 (简化版, 用默认值)\033[0m")
            result = create_skill(
                title="test-skill",
                summary="测试技能",
                read_when=["测试", "test"],
                content="# Test Skill\n\n这是一个测试技能。"
            )
            print(f"\033[32m{result}\033[0m")
            continue

        if cmd == "audit":
            # Demonstrate P0/P1/P2 audit
            test_cases = [
                ("安全技能", "# Safe Skill\n\n运行 git status"),
                ("网络技能", "# Network Skill\n\ncurl https://api.example.com"),
                ("危险技能", "# Danger Skill\n\nos.system('rm -rf /')"),
            ]
            print("\n\033[90m安全审计演示:\033[0m")
            for name, content in test_cases:
                level, report = audit_skill(content)
                color = {"P0": "31", "P1": "33", "P2": "32"}[level]
                print(f"  \033[{color}m[{level}] {name}: {report}\033[0m")
            continue

        if cmd == "stats":
            loaded_count = sum(1 for s in skill_index if s.loaded)
            total_content = sum(len(s.content) for s in loaded_skills)
            print(f"\033[90m技能总数: {len(skill_index)}\033[0m")
            print(f"\033[90m已加载: {loaded_count}\033[0m")
            print(f"\033[90m已加载内容: {total_content:,} 字符\033[0m")
            print(f"\033[90m索引大小: ~{len(skill_index) * 50} tokens\033[0m")
            continue

        # Auto-match skill before sending to agent
        matched = match_skill(query)
        if matched:
            print(f"\033[35m[技能匹配] 检测到触发词, 建议加载: {matched}\033[0m")
            # Auto-load the matched skill
            if not any(s.title == matched and s.loaded for s in skill_index):
                load_skill(matched)
                print(f"\033[35m[技能匹配] '{matched}' 已自动加载到上下文\033[0m")

        # Send to agent
        history.append({"role": "user", "content": query})
        agent_loop(history)

        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)
        print()
