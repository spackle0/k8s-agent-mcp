# CLAUDE.md

Project context for Claude Code. Updated as the project evolves.

---

## Project Overview

**k8s-agent-mcp** — An agentic AI system for Kubernetes troubleshooting. An LLM (via Ollama) reasons over a set of MCP tools that query a live Kubernetes cluster, enabling conversational troubleshooting without manual kubectl usage.

---

## Repository Structure

```
services/
  mcp_k8s_server/
    app/
      server.py             # FastMCP server — defines @mcp.tool() functions
      k8s_client.py         # Thin wrapper around the kubernetes Python client
      prometheus_client.py  # Prometheus HTTP API client (PromQL queries)
    tests/
      test_smoke.py   # Smoke tests with FakeK8sClient
  agent_chatbot/
    app/
      agent.py        # Interactive LLM chatbot with agentic tool loop
    tests/
      .gitkeep        # Placeholder so git tracks the empty directory
deploy/
  rbac-readonly.yaml  # K8s RBAC for in-cluster service account
docker/
  mcp-server.Dockerfile
  agent.Dockerfile
scripts/
  run_tests.sh        # pytest runner; treats exit codes 4/5 as success
.github/
  workflows/
    ci.yaml           # CI: runs tests on push/PR to main
cluster.yaml          # k3d cluster definition (name: k8s-agent, 1 server, 2 agents)
docker-compose.yaml
pyproject.toml        # uv-managed dependencies
```

---

## Architecture

Two separate services communicate over HTTP:

```
agent.py  ──(FastMCP streamable-HTTP)──▶  server.py  ──▶  k8s_client.py  ──▶  K8s API
```

- **MCP server** (`server.py`): Exposes Kubernetes query functions as MCP tools via FastMCP standalone. Runs on `http://localhost:8000/mcp`.
- **Agent** (`agent.py`): Interactive chatbot. Fetches tools at startup, then runs a conversation loop where the LLM reasons over tools and calls them in an agentic loop (multiple tool calls per turn until the LLM has enough information to answer).
- **k8s_client.py**: Lazy-initialized Kubernetes API clients. Tries in-cluster config first, falls back to local kubeconfig.

---

## Tech Stack

| Component | Choice |
|---|---|
| MCP framework | `fastmcp` standalone (≥3.0.2) — **not** `mcp.server.fastmcp` (SDK bundled version) |
| LLM runtime | Ollama — model `llama3.1:8b` |
| K8s client | `kubernetes` Python client (≥35.0.0) |
| HTTP client | `httpx` (async) |
| Package manager | `uv` |
| Linter | `ruff` |
| Local cluster | k3d |
| Planned API | FastAPI + uvicorn (alerting webhook) |

**Important**: Always import from `fastmcp` — do not import from `mcp.server.fastmcp`.
```python
from fastmcp import FastMCP, Client
```

---

## Current MCP Tools

Defined in `server.py`, implemented in `k8s_client.py`:

| Tool | Signature | Returns |
|---|---|---|
| `list_namespaces` | `() -> list[str]` | Namespace name strings |
| `list_pods` | `(namespace: str) -> list[dict]` | Pod status dicts (name, phase, ready, restart_count, reason) |
| `read_pod_log` | `(namespace: str, pod: str, container: str \| None, tail_lines: int) -> str` | Last N lines of pod logs |
| `query_prometheus` | `(query: str) -> list[dict]` | Instant PromQL query results (metric labels, value, timestamp) |

---

## Key Conventions

### MCP Tool Docstrings
Docstrings on `@mcp.tool()` functions are sent to the LLM as part of the tool definition. They must:
- Describe **what the tool does** (not implementation details like "uses in-cluster config")
- Document the **return structure** explicitly — field names, types, and what they mean
- State if the tool **takes no arguments** to prevent the LLM hallucinating parameters

```python
@mcp.tool()
def list_pods(namespace: str) -> list[dict]:
    """List all pods in a given namespace with their current status.

    Takes a namespace string and returns a list of dicts, each with:
      - name: pod name
      - phase: Running, Pending, Failed, Succeeded, Unknown
      - ready: true if all containers are passing readiness checks
      - restart_count: total restarts across all containers
      - reason: waiting reason (e.g. CrashLoopBackOff) or null
    """
```

### Tool Return Types
MCP tools must return JSON-serializable types. The kubernetes Python client returns `V1Pod` and similar objects that **cannot** be serialized — always extract fields explicitly into plain dicts or strings. In this project, `k8s_client.py` handles extraction so `server.py` tools can return its output directly:

```python
# k8s_client.py extracts fields into a plain dict — safe to return from MCP tool
return k8s_client.list_pods(namespace)

# Never return raw kubernetes client objects from a tool
return core_api.list_namespaced_pod(namespace=namespace)  # Wrong — not serializable
```

### Tool Design Philosophy
- **Tools fetch data; the LLM reasons over it.** Don't create narrow filter tools like `get_crashlooping_pods` — instead return enough data from `list_pods` for the LLM to identify the problem itself.
- A new tool is warranted when it requires a **different API call**, not just filtering existing data.

### Agent Tool Result Extraction
`call_tool` in `agent.py` extracts `result.content[0].text` — the plain text string from the MCP result — before passing it to the LLM. Do not pass the raw `CallToolResult` object.

---

## Workflow Preferences

- Do not commit by default. Make code changes and stop. The user reviews `git diff` before deciding to commit. Only commit when explicitly asked.
- Active branch: `mcp_even_more_tools`. If the branch does not exist, check for the current branch and switch to it, then update this file.
- The worktree `claude/gallant-turing` should be kept in sync with `mcp_even_more_tools` when resuming sessions (`git reset --hard <sha>`).
- When committing, always use the `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` trailer.
- The user uses PyCharm (`.idea/` present) and ruff for linting.
- Avoid the use of emojis and em-dashes in any veribage or documentation created
- Avoid sycophancy in suggestions. Challenge me and suggest better ways of doing things.

---

## Planned Features

1. **`get_events` tool** — Kubernetes events are often the first place to look when troubleshooting
2. **FastAPI alerting webhook** — stateless endpoint that accepts alert payloads (Prometheus/Alertmanager format), runs the agent, returns structured diagnosis. Persistent MCP client via FastAPI lifespan, asyncio.Lock for concurrent request safety.
3. **Agentic loop safety** — consider a max iterations guard on the `while True` loop in `run_turn()`

---

## Environment Variables

Configuration is managed via a `.env` file that is not committed to version control.

- `.env.template` — committed, contains all variables with safe defaults and masked secrets
- `.env` — local only, listed in `.gitignore`, created by copying the template

**Convention**: whenever a new env var is added, update `.env.template` with a safe default or masked placeholder (e.g. `API_KEY="your-api-key-here"`). Never put real credentials in `.env.template`.

| Variable | Default | Used by |
|---|---|---|
| `PROMETHEUS_URL` | `http://localhost:9090` | `prometheus_client.py` |
| `MCP_SERVER_URL` | `http://localhost:8000/mcp` | `agent.py` |
| `OLLAMA_HOST` | `http://localhost:11434` | ollama client (auto-detected) |

---

## Local Development

Copy the env template before first run:
```bash
cp .env.template .env
```

Create and start the k3d cluster (required for K8s tools):
```bash
make cluster-create   # first time only
make cluster-start
```

Start Ollama and pull the model (required for the agent):
```bash
ollama serve          # starts the Ollama server on localhost:11434
ollama pull llama3.1:8b
```

Or use the Makefile target which does both:
```bash
make ollama
```

Run the MCP server:
```bash
uv run python -m services.mcp_k8s_server.app.server
```

Run the agent chatbot (requires MCP server already running):
```bash
uv run python -m services.agent_chatbot.app.agent
```

Or start both together with:
```bash
make start
```
