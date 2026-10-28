import asyncio

import pytest
from conftest import INSTRUCTIONS, TOKEN

from langchain_pethost import PethostError, PethostToolkit


def test_without_a_token_it_says_where_to_make_one(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PETHOST_TOKEN", raising=False)
    with pytest.raises(PethostError, match=r"PETHOST_TOKEN.*API tokens"):
        PethostToolkit()


def test_the_token_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PETHOST_TOKEN", " pth_environment\n")
    assert PethostToolkit().token.get_secret_value() == "pth_environment"
    assert "pth_environment" not in repr(PethostToolkit())


def test_the_tools_are_the_servers(mcp_url: str) -> None:
    tools = PethostToolkit(token=TOKEN, url=mcp_url).get_tools()
    assert {tool.name: tool.description for tool in tools} == {
        "GetMachine": "Gets the machine: its projects and what is wrong.",
        "CreateProject": "Creates a project from its files and deploys it.",
    }


def test_read_only_keeps_the_tools_the_server_marks_so(mcp_url: str) -> None:
    tools = PethostToolkit(token=TOKEN, url=mcp_url, read_only=True).get_tools()
    assert [tool.name for tool in tools] == ["GetMachine"]


def test_a_tool_runs_from_synchronous_and_asynchronous_code(mcp_url: str) -> None:
    tools = {tool.name: tool for tool in PethostToolkit(token=TOKEN, url=mcp_url).get_tools()}
    create = tools["CreateProject"]

    assert _text(create.invoke({"project_id": "notes"})) == "created notes"
    assert _text(asyncio.run(create.ainvoke({"project_id": "blog"}))) == "created blog"


def test_synchronous_calls_work_inside_a_running_event_loop(mcp_url: str) -> None:
    toolkit = PethostToolkit(token=TOKEN, url=mcp_url)

    async def in_a_notebook() -> str:
        machine = toolkit.get_tools()[0]
        return _text(machine.invoke({}))

    assert asyncio.run(in_a_notebook()) == "machine sam: 1 project, nothing wrong"


def test_the_instructions_are_the_servers(mcp_url: str) -> None:
    toolkit = PethostToolkit(token=TOKEN, url=mcp_url)
    assert toolkit.get_instructions() == INSTRUCTIONS
    assert asyncio.run(toolkit.aget_instructions()) == INSTRUCTIONS


def test_a_refused_token_says_so(mcp_url: str) -> None:
    toolkit = PethostToolkit(token="pth_revoked", url=mcp_url)
    with pytest.raises(PethostError, match="refused the API token"):
        toolkit.get_tools()
    with pytest.raises(PethostError, match="refused the API token"):
        asyncio.run(toolkit.aget_instructions())


def _text(content: object) -> str:
    """The text of a tool's answer: the adapter gives MCP's content as LangChain's blocks."""
    if isinstance(content, str):
        return content
    assert isinstance(content, list)
    return "".join(block["text"] for block in content)
