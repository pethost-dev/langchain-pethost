"""A stand-in for Pethost's MCP server, made as Pethost's is: stateless, answering in JSON, and
refusing a request without its bearer token with a 401."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from starlette.types import ASGIApp, Receive, Scope, Send

TOKEN = "pth_test"
INSTRUCTIONS = "Pethost is the user's hosting. Start with GetMachine."


def _server() -> FastMCP:
    server = FastMCP("pethost", instructions=INSTRUCTIONS, stateless_http=True, json_response=True)

    @server.tool(name="GetMachine", annotations=ToolAnnotations(readOnlyHint=True))
    def get_machine() -> str:
        """Gets the machine: its projects and what is wrong."""
        return "machine sam: 1 project, nothing wrong"

    @server.tool(name="CreateProject", annotations=ToolAnnotations(readOnlyHint=False))
    def create_project(project_id: str) -> str:
        """Creates a project from its files and deploys it."""
        return f"created {project_id}"

    return server


def _with_token(app: ASGIApp) -> ASGIApp:
    async def guarded(scope: Scope, receive: Receive, send: Send) -> None:
        headers = dict(scope.get("headers", []))
        if scope["type"] == "http" and headers.get(b"authorization") != f"Bearer {TOKEN}".encode():
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b""})
            return
        await app(scope, receive, send)

    return guarded


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture(scope="session")
def mcp_url() -> Iterator[str]:
    """The stand-in's MCP endpoint, served on a thread for the whole session."""
    port = _free_port()
    app = _with_token(_server().streamable_http_app())
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)

    yield f"http://127.0.0.1:{port}/mcp"

    server.should_exit = True
    thread.join()
