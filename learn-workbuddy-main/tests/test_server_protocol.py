from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from conftest import NO_PROXY_OPENER


HEADER = {"X-Mini-WorkBuddy-Request": "1"}


def request_json(url: str, payload: dict | None = None, headers: dict | None = None) -> dict:
    headers = headers or {}
    data = None
    if payload is not None:
        headers = {"Content-Type": "application/json", **headers}
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers)
    with NO_PROXY_OPENER.open(req, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def test_health_endpoint_is_public(mini_server: str) -> None:
    assert request_json(mini_server + "/api/v1/health") == {"data": {"status": "ok"}}


def test_protected_endpoints_require_request_header(mini_server: str) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc:
        request_json(mini_server + "/api/v1/sessions")
    assert exc.value.code == 403


def test_run_endpoint_creates_session_and_history(mini_server: str) -> None:
    result = request_json(
        mini_server + "/api/v1/runs",
        {"cwd": ".", "prompt": "list files"},
        HEADER,
    )

    data = result["data"]
    session_id = data["session"]["id"]
    assert "README.md" in data["answer"]

    history = request_json(mini_server + f"/api/v1/sessions/{session_id}/history", headers=HEADER)
    events = history["data"]
    assert [event["type"] for event in events] == [
        "message",
        "tool_call",
        "tool_result",
        "message",
    ]
    assert events[1]["tool_call_id"] == events[2]["tool_call_id"]


def test_acp_initialize_new_prompt_and_load(mini_server: str) -> None:
    init = request_json(
        mini_server + "/api/v1/acp",
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        HEADER,
    )
    assert init["result"]["serverInfo"]["name"] == "mini-workbuddy"

    new_session = request_json(
        mini_server + "/api/v1/acp",
        {"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {"cwd": ".", "title": "ACP"}},
        HEADER,
    )
    session_id = new_session["result"]["sessionId"]

    prompt = request_json(
        mini_server + "/api/v1/acp",
        {"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": session_id, "prompt": "tools"}},
        HEADER,
    )
    assert "tool_search" in prompt["result"]["answer"]

    loaded = request_json(
        mini_server + "/api/v1/acp",
        {"jsonrpc": "2.0", "id": 4, "method": "session/load", "params": {"sessionId": session_id}},
        HEADER,
    )
    assert loaded["result"]["sessionId"] == session_id
    history = loaded["result"]["history"]
    assert len(history) == 4
    assert history[1]["tool_call_id"] == history[2]["tool_call_id"]


def test_acp_unknown_method_returns_jsonrpc_error(mini_server: str) -> None:
    response = request_json(
        mini_server + "/api/v1/acp",
        {"jsonrpc": "2.0", "id": 99, "method": "nope", "params": {}},
        HEADER,
    )
    assert response["error"]["code"] == -32601
