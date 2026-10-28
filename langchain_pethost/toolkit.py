"""PethostToolkit: the tools of Pethost's MCP server, as LangChain tools.

The server is the one source of the tools: their names, descriptions, input schemas and
annotations are what it lists when the tools are loaded, so a tool it adds or changes reaches an
agent with no release of this package. Each call opens its own MCP session, as the server keeps
no state between requests.
"""

from __future__ import annotations

import asyncio
import contextvars
import os
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version
from typing import Any, TypeVar

import httpx
from langchain_core.tools import BaseTool, BaseToolkit, StructuredTool
from langchain_mcp_adapters.server_info import load_mcp_server_info
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from langchain_mcp_adapters.tools import load_mcp_tools
from pydantic import Field, SecretStr

MCP_URL = "https://mcp.pethost.dev/mcp"
TOKEN_VARIABLE = "PETHOST_TOKEN"  # As Pethost's SDKs and its CLI read it.
TOKENS_PAGE = "https://console.pethost.dev/settings"
USER_AGENT = f"langchain-pethost/{version('langchain-pethost')}"

T = TypeVar("T")


class PethostError(Exception):
    """Pethost has no token to go on, or refused the one it was given."""


def _token_from_environment() -> SecretStr:
    token = os.environ.get(TOKEN_VARIABLE, "").strip()
    if not token:
        raise PethostError(
            f"No Pethost API token: set {TOKEN_VARIABLE}, or pass token=. "
            f"Make one in the panel's Settings, under API tokens: {TOKENS_PAGE}"
        )
    return SecretStr(token)


class PethostToolkit(BaseToolkit):
    """The tools of Pethost's MCP server, for a LangChain or LangGraph agent.

    With them an agent deploys Docker Compose projects to the account's Pethost machine, reads
    their logs and HTTP requests, runs commands in their containers, rolls back, and makes
    Postgres and Valkey databases.

    Example:
        ```python
        from langchain.agents import create_agent
        from langchain_pethost import PethostToolkit

        toolkit = PethostToolkit()  # reads PETHOST_TOKEN
        agent = create_agent(
            "anthropic:claude-opus-5-5",
            tools=toolkit.get_tools(),
            system_prompt=toolkit.get_instructions(),
        )
        ```

    The tools run from synchronous code (`agent.invoke`) and from asynchronous code
    (`await agent.ainvoke`); `aget_tools` and `aget_instructions` load them without blocking.
    """

    token: SecretStr = Field(default_factory=_token_from_environment, repr=False)
    """An API token from the panel's Settings. Absent: the PETHOST_TOKEN variable."""

    url: str = MCP_URL
    """The MCP endpoint."""

    read_only: bool = False
    """Only the tools the server marks read-only: the machine, projects, logs, requests, files."""

    def get_tools(self) -> list[BaseTool]:
        """The server's tools, each callable from synchronous and asynchronous code."""
        return _run(self.aget_tools())

    async def aget_tools(self) -> list[BaseTool]:
        """As `get_tools`, without blocking the event loop."""
        tools = await _calling_pethost(
            load_mcp_tools(None, connection=self._connection(), server_name="pethost")
        )
        if self.read_only:
            tools = [tool for tool in tools if (tool.metadata or {}).get("readOnlyHint")]
        for tool in tools:
            _make_synchronous(tool)
        return tools

    def get_instructions(self) -> str:
        """What the server tells an agent of Pethost and its tools: for the system prompt."""
        return _run(self.aget_instructions())

    async def aget_instructions(self) -> str:
        """As `get_instructions`, without blocking the event loop."""
        info = await _calling_pethost(load_mcp_server_info(None, connection=self._connection()))
        return info.instructions or ""

    def _connection(self) -> StreamableHttpConnection:
        return {
            "transport": "streamable_http",
            "url": self.url,
            "headers": {
                "Authorization": f"Bearer {self.token.get_secret_value()}",
                "User-Agent": USER_AGENT,
            },
        }


async def _calling_pethost(call: Coroutine[Any, Any, T]) -> T:
    """Awaits a call to the server, and says so plainly when it refused the token."""
    try:
        return await call
    except Exception as error:
        if _refused(error):
            raise PethostError(
                "Pethost refused the API token (HTTP 401): it was revoked, or mistyped. "
                f"Make a new one in the panel's Settings, under API tokens: {TOKENS_PAGE}"
            ) from error
        raise


def _refused(error: BaseException) -> bool:
    """Whether a 401 is in the error: the transport raises it inside a task group's group."""
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 401
    inner = list(getattr(error, "exceptions", ()))
    if error.__cause__ is not None:
        inner.append(error.__cause__)
    return any(_refused(each) for each in inner)


def _make_synchronous(tool: BaseTool) -> None:
    """Gives an MCP tool, which the adapter makes asynchronous only, a synchronous path too."""
    if not isinstance(tool, StructuredTool) or tool.coroutine is None or tool.func is not None:
        return
    tool.func = _synchronous(tool.coroutine)


def _synchronous(coroutine: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., T]:
    def call(**arguments: Any) -> T:
        return _run(coroutine(**arguments))

    return call


def _run(call: Coroutine[Any, Any, T]) -> T:
    """Runs a coroutine to its end from synchronous code.

    Inside a running event loop (a notebook's, or a synchronous tool called from asynchronous
    code), it runs on a thread of its own: a loop cannot wait on itself.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(call)

    context = contextvars.copy_context()  # The caller's tracing and callbacks go along.
    with ThreadPoolExecutor(max_workers=1) as thread:
        return thread.submit(context.run, asyncio.run, call).result()
