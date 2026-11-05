from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from .audit import AuditLog
from .agent import MiniAgent
from .config import HarnessConfig
from .events import EventBus
from .storage import Storage
from .tools import ToolRegistry


class HarnessRuntime:
    def __init__(self, config: HarnessConfig) -> None:
        self.config = config
        self.storage = Storage(config)
        self.events = EventBus()
        self.tools = ToolRegistry(config, self.storage)
        self.audit = AuditLog(config)
        # A previous process may have stopped after the durable JSONL append
        # but before publishing audit.head.  Recover only that one provable
        # state; ambiguous or tampered histories prevent runtime startup.
        self.audit_recovered = self.audit.recover_interrupted_append()
        self.agent = MiniAgent(self.storage, self.tools, self.events, self.audit)


def make_handler(runtime: HarnessRuntime) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MiniWorkBuddy/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/health":
                self.json({"data": {"status": "ok"}})
            elif parsed.path == "/api/v1/sessions":
                if not self.require_header():
                    return
                self.json({"data": [record.__dict__ for record in runtime.storage.list_sessions()]})
            elif parsed.path.startswith("/api/v1/sessions/") and parsed.path.endswith("/history"):
                if not self.require_header():
                    return
                session_id = parsed.path.split("/")[4]
                record = runtime.storage.load_session(session_id)
                self.json({"data": runtime.storage.read_transcript(record)})
            elif parsed.path == "/api/v1/acp/events":
                if not self.require_header():
                    return
                self.sse()
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/v1/sessions":
                if not self.require_header():
                    return
                body = self.body()
                cwd = body.get("cwd") or "."
                title = body.get("title") or "Untitled"
                record = runtime.storage.create_session(cwd, title)
                self.json({"data": record.__dict__})
            elif parsed.path == "/api/v1/runs":
                if not self.require_header():
                    return
                body = self.body()
                cwd = body.get("cwd") or "."
                prompt = body.get("prompt") or ""
                record = runtime.storage.create_session(cwd, prompt[:60] or "Run")
                result = runtime.agent.prompt(record, prompt)
                self.json({"data": {"session": record.__dict__, **result}})
            elif parsed.path == "/api/v1/acp":
                if not self.require_header():
                    return
                self.handle_acp()
            else:
                self.error(HTTPStatus.NOT_FOUND, "not found")

        def handle_acp(self) -> None:
            message = self.body()
            method = message.get("method")
            params = message.get("params") or {}
            request_id = message.get("id")
            try:
                if method == "initialize":
                    result: Any = {"protocolVersion": 1, "serverInfo": {"name": "mini-workbuddy", "version": "0.1"}}
                elif method == "session/new":
                    record = runtime.storage.create_session(params.get("cwd") or ".", params.get("title") or "ACP Session")
                    result = {"sessionId": record.id}
                elif method == "session/load":
                    record = runtime.storage.load_session(params["sessionId"])
                    result = {"sessionId": record.id, "history": runtime.storage.read_transcript(record)}
                elif method == "session/prompt":
                    record = runtime.storage.load_session(params["sessionId"])
                    result = runtime.agent.prompt(record, params.get("prompt") or "")
                else:
                    self.json({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "method not found"}})
                    return
                self.json({"jsonrpc": "2.0", "id": request_id, "result": result})
            except Exception as exc:  # Teaching server: surface errors plainly.
                self.json({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": str(exc)}})

        def sse(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            for event in runtime.events.subscribe():
                try:
                    self.wfile.write(event.to_sse())
                    self.wfile.flush()
                except OSError:
                    break

        def require_header(self) -> bool:
            if self.headers.get(runtime.config.request_header) != runtime.config.request_header_value:
                self.error(
                    HTTPStatus.FORBIDDEN,
                    f"missing {runtime.config.request_header}: {runtime.config.request_header_value}",
                )
                return False
            return True

        def body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length == 0:
                return {}
            raw = self.rfile.read(length)
            return json.loads(raw.decode("utf-8"))

        def json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def error(self, status: HTTPStatus, message: str) -> None:
            self.json({"error": {"message": message}}, status)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler


class SafeThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        return


def run_server(port: int, host: str = "127.0.0.1") -> None:
    runtime = HarnessRuntime(HarnessConfig.from_env())
    handler = make_handler(runtime)
    httpd = SafeThreadingHTTPServer((host, port), handler)
    print(f"Mini WorkBuddy listening on http://{host}:{port}")
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    run_server(args.port, args.host)


if __name__ == "__main__":
    main()
