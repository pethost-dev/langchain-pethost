# langchain-pethost

[Pethost](https://pethost.dev)'s tools for LangChain and LangGraph agents. With them an agent
deploys Docker Compose projects, reads their logs and HTTP requests, runs commands in their
containers, rolls back, and makes Postgres and Valkey databases.

The tools are those of Pethost's MCP server, `https://mcp.pethost.dev/mcp`, loaded through
[langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters). Their names,
descriptions and input schemas come from the server, so a tool it adds reaches your agent without
a new release of this package.

[Deploy an app from a LangChain agent](https://pethost.dev/blog/deploy-app-from-langchain-agent/)
takes an agent from an empty account to a running app, its logs and its requests, with what each
step printed.

## Install

```sh
pip install langchain-pethost
```

The examples below also use `langchain` and `langchain-anthropic`.

## A token

In the panel's [Settings](https://console.pethost.dev/settings), under API tokens, create a token
and copy it: it is not shown again.

```sh
export PETHOST_TOKEN=pth_…
```

A program with the token can deploy to and manage your machine, and cannot change your account.
The token does not expire: revoke it in Settings when you no longer need it.

## An agent that deploys

```python
from langchain.agents import create_agent
from langchain_pethost import PethostToolkit

toolkit = PethostToolkit()  # reads PETHOST_TOKEN
agent = create_agent(
    "anthropic:claude-opus-5-5",
    tools=toolkit.get_tools(),
    system_prompt=toolkit.get_instructions(),
)

result = agent.invoke(
    {"messages": [("user", "Deploy a small Flask app that says hello, and give me its address.")]}
)
print(result["messages"][-1].content)
```

`get_instructions()` is what the server tells an agent about Pethost: where to start, how a
project's compose.yaml is written, what its errors mean. Give it as the system prompt, or as part
of yours.

Every tool runs from synchronous code, as above, and from asynchronous code:

```python
tools = await toolkit.aget_tools()
instructions = await toolkit.aget_instructions()
agent = create_agent("anthropic:claude-opus-5-5", tools=tools, system_prompt=instructions)
result = await agent.ainvoke({"messages": [("user", "Why does my blog answer 502?")]})
```

## An agent that only looks

```python
toolkit = PethostToolkit(read_only=True)
```

Only the tools the server marks read-only: the machine, projects, operations, commits, logs,
requests and files. Such an agent finds out why a site fails, and changes nothing.

## The tools

| Tool | What it does | Read-only |
|---|---|---|
| `GetMachine` | The machine, every project with its problems and its address. Where an agent starts. | yes |
| `GetProject` | One project in full: its services, volumes, addresses, recent deploys and backups. | yes |
| `CreateProject` | Creates a project from its files, an archive or a GitHub repository, and deploys it. | |
| `DeployProject` | Deploys a new version: changed files, another commit, or an earlier deploy back. | |
| `RunProjectAction` | Starts, stops or restarts services, backs up, restores, deletes the project. | |
| `GetOperation` | Waits for a deploy, backup or restore to end, with its log if it failed. | yes |
| `ListCommits` | The commits of a GitHub project's branch. | yes |
| `QueryHttpTraffic` | The requests that reached a project: which paths fail, which are slow. | yes |
| `QueryContainerLogs` | The containers' output. | yes |
| `ReadPath` | A file or a directory of the project or of a container. | yes |
| `RunServiceCommand` | Runs a command in a service's container. | |
| `CreateDatabase` | Makes a Postgres or Valkey database. | |
| `LinkDatabase` | Lets projects reach a database. | |
| `SetProjectAlerts` | What Pethost watches on a project, and when it tells you. | |
| `RunMachineAction` | Adds or removes an SSH key, ends a session, schedules a restart. | |
| `CreateTransfer` | A URL that moves one file between a shell and the machine. | |

An agent with no shell sends a project's files as text, in `CreateProject`'s `files`;
`CreateTransfer` is for an agent that can run `curl`.

## Options

| Argument | Default | |
|---|---|---|
| `token` | `PETHOST_TOKEN` | An API token from Settings. |
| `url` | `https://mcp.pethost.dev/mcp` | The MCP endpoint. |
| `read_only` | `False` | Only the tools that change nothing. |

## Errors

Without a token, or with one Pethost refuses, the toolkit raises `PethostError`, which says where
to make one. When a tool's call is refused (a project that does not exist, a compose.yaml with a
mistake), the server's words go back to the model as the tool's error, so the agent can correct
its call.

## About Pethost

Pethost is managed hosting for Docker Compose projects. A plan has a set size in CPU, memory and
disk, at one flat price, for as many projects as fit. Pethost's software deploys them, gives them
HTTPS addresses, keeps their request logs and backs them up every night. You run it through your
agent or from a web panel: both show the same projects, logs and requests.

- **Always on:** no cold starts, nothing sleeps, on every plan. Security updates install
  themselves.
- **HTTPS addresses:** anything.yourname.pethost.app at once, or your own domain with one DNS
  record. Certificates renew themselves.
- **Deploys from GitHub:** every push deploys itself, and an earlier commit is one step back.
- **Request logs:** every request with its status and time, the busiest paths and the error rate,
  kept for 30 days.
- **Nightly backups:** encrypted, stored off the machine, kept for 14 days.
- **Docker Compose, as written:** a project is a Compose file, and the same file runs anywhere
  else Docker does. A database is one click, Postgres or Valkey, at no extra cost.

**Pricing.** Starter is €9.99 a month for 2 vCPU, 3 GB of memory and 30 GB of SSD. Grow is €17.99
for 4 vCPU, 6 GB and 60 GB. Scale is €59 for 8 vCPU, 30 GB and 200 GB. Prices are without VAT.
There is no free tier. [See the plans](https://pethost.dev/#pricing).

## License

MIT
