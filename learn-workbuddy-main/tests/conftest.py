from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@pytest.fixture()
def root() -> Path:
    return ROOT


@pytest.fixture()
def mini_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "mini-home"
    monkeypatch.setenv("MINI_WORKBUDDY_HOME", str(home))
    return home


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_url(url: str, headers: dict[str, str] | None = None, timeout: float = 8) -> None:
    deadline = time.time() + timeout
    headers = headers or {}
    while True:
        try:
            req = urllib.request.Request(url, headers=headers)
            with NO_PROXY_OPENER.open(req, timeout=1):
                return
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if time.time() > deadline:
                raise
            time.sleep(0.05)


@pytest.fixture()
def mini_server(tmp_path: Path):
    port = free_port()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["MINI_WORKBUDDY_HOME"] = str(tmp_path / "server-home")
    proc = subprocess.Popen(
        [sys.executable, "-m", "mini_workbuddy.server", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_for_url(f"http://127.0.0.1:{port}/api/v1/health")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
