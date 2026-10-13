from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HarnessConfig:
    root_dir: Path
    max_inline_output: int = 30_000
    tool_result_threshold: int = 50 * 1024
    request_header: str = "X-Mini-WorkBuddy-Request"
    request_header_value: str = "1"

    @classmethod
    def from_env(cls) -> "HarnessConfig":
        root = Path(os.environ.get("MINI_WORKBUDDY_HOME", "~/.mini_workbuddy")).expanduser()
        max_inline = int(os.environ.get("MINI_WORKBUDDY_MAX_INLINE_OUTPUT", "30000"))
        threshold_kb = int(os.environ.get("MINI_WORKBUDDY_TOOL_RESULT_THRESHOLD_KB", "50"))
        return cls(root_dir=root, max_inline_output=max_inline, tool_result_threshold=threshold_kb * 1024)

    @property
    def projects_dir(self) -> Path:
        return self.root_dir / "projects"

    @property
    def sessions_dir(self) -> Path:
        return self.root_dir / "sessions"

    @property
    def memory_dir(self) -> Path:
        return self.root_dir / "memory"

    @property
    def audit_dir(self) -> Path:
        return self.root_dir / "audit"

    def ensure_dirs(self) -> None:
        for path in [
            self.root_dir,
            self.projects_dir,
            self.sessions_dir,
            self.memory_dir,
            self.audit_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)


def workspace_id(cwd: str) -> str:
    cleaned = cwd.strip("/").replace("/", "-").replace(" ", "_")
    return cleaned or "root"
