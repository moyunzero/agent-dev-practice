from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SidecarSession:
    id: str
    port: int
    process: subprocess.Popen[str]


class SidecarManager:
    """Tiny sidecar manager inspired by WorkBuddy's control socket pattern."""

    def __init__(self, socket_path: Path | None = None) -> None:
        self.socket_path = socket_path or Path(tempfile.gettempdir()) / "mini-workbuddy-sidecar.sock"
        self.sessions: dict[str, SidecarSession] = {}
        self._server: socket.socket | None = None

    def start(self) -> None:
        if self.socket_path.exists():
            self.socket_path.unlink()
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.bind(str(self.socket_path))
        self._server.listen(8)
        print(f"sidecar control socket: {self.socket_path}")
        while True:
            client, _ = self._server.accept()
            threading.Thread(target=self._handle_client, args=(client,), daemon=True).start()

    def _handle_client(self, client: socket.socket) -> None:
        with client:
            raw = client.recv(65536).decode("utf-8")
            try:
                request = json.loads(raw)
                result = self.dispatch(request.get("method"), request.get("params") or {})
                response = {"jsonrpc": "2.0", "id": request.get("id"), "result": result}
            except Exception as exc:
                response = {"jsonrpc": "2.0", "id": None, "error": {"message": str(exc)}}
            client.sendall(json.dumps(response).encode("utf-8"))

    def dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "session.create":
            return self.create_session(params)
        if method == "session.kill":
            return self.kill_session(params["sessionId"])
        if method == "session.list":
            return {"sessions": [{"id": s.id, "port": s.port, "pid": s.process.pid} for s in self.sessions.values()]}
        raise ValueError(f"unknown method: {method}")

    def create_session(self, params: dict[str, Any]) -> dict[str, Any]:
        session_id = params["sessionId"]
        port = int(params["port"])
        process = subprocess.Popen(
            [sys.executable, "-m", "mini_workbuddy.server", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env={**os.environ},
        )
        self.sessions[session_id] = SidecarSession(session_id, port, process)
        return {"sessionId": session_id, "port": port, "pid": process.pid, "acpEndpoint": f"http://127.0.0.1:{port}/api/v1/acp"}

    def kill_session(self, session_id: str) -> dict[str, Any]:
        session = self.sessions.pop(session_id)
        session.process.terminate()
        return {"killed": True}


def main() -> None:
    SidecarManager().start()


if __name__ == "__main__":
    main()

