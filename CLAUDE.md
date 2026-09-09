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
  workloads/
    test-workload.yaml    # example-web Deployment + Service + ServiceMonitor
    blackbox-probe.yaml   # Probe CR for blackbox exporter latency monitoring
  chaosmesh/
    chaosmesh-rbac.yaml            # RBAC required by Chaos Mesh
    chaosmesh-pod-kill-cron.yaml   # PodChaos, pod-kill on a cron
    chaosmesh-pod-cpu-stress.yaml  # StressChaos, 80% CPU
    chaosmesh-network-delay.yaml   # NetworkChaos, 200ms +/- 50ms
    chaosmesg-pod-failure-5m.yaml  # PodChaos, pod failure for 5m (filename typo)
docs/
  blog-series-outline.md  # Outline for the write-up series
docker/
  mcp-server.Dockerfile
  agent.Dockerfile
scripts/
  run_tests.sh        # pytest runner; treats exit codes 4/5 as success
.github/
  workflows/
    ci.yaml           # CI: runs tests on push/PR to main
cluster.yaml          # k3d cluster definition (name: k8s-agent, 1 server, 2 agents)
ideas.md              # Roadmap scratchpad
Makefile              # Primary entry point; `make` alone prints help
docker-compose.yaml
pyproject.toml        # uv-managed dependencies
```

---

## Architecture

Two separate services communicate over HTTP:

```
                                          ┌─▶ k8s_client.py ──────▶ K8s API
agent.py ──(FastMCP streamable-HTTP)──▶ server.py
    │                                     └─▶ prometheus_client.py ─▶ Prometheus
    └──▶ Ollama
```

- **MCP server** (`server.py`): Exposes Kubernetes query functions as MCP tools via FastMCP standalone. Runs on `http://localhost:8000/mcp`.
- **Agent** (`agent.py`): Interactive chatbot. Fetches tools at startup, then runs a conversation loop where the LLM reasons over tools and calls them in an agentic loop (multiple tool calls per turn until the LLM has enough information to answer).
- **k8s_client.py**: Lazy-initialized Kubernetes API clients. Tries in-cluster config first, falls back to local kubeconfig.
- **prometheus_client.py**: Stateless `httpx` calls to the Prometheus HTTP API for instant PromQL queries.

**Trust boundary**: the MCP server is the only component holding cluster
credentials, and it exposes a fixed read-only tool vocabulary. The agent has no
cluster access, and the compose file deliberately gives it no kubeconfig. Keep
it that way. Anything that would let the agent construct arbitrary API calls (a
generic `kubectl` passthrough tool, raw field selectors, a `patch`/`apply` tool)
collapses the boundary and should be argued for explicitly rather than added for
convenience.

Read-only is also the mitigation for prompt injection: pod logs and metric
labels are attacker-influenced data flowing into the model's context. Today the
worst case is a wrong answer. Adding a write tool changes that category
entirely.

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
| Local cluster | k3d (see `cluster.yaml`) |
| Target cluster | Homelab bare metal on a Dell R630 |
| Observability | Prometheus Operator, blackbox exporter |
| Fault injection | Chaos Mesh |
| Planned API | FastAPI + uvicorn (alerting webhook) |

**Cluster policy**: k3d is the working default and the path documented in the
README, because it lets a reader spin up a throwaway cluster in a minute. The
R630 homelab is the eventual target. Nothing in the code depends on either:
`k8s_client.py` loads in-cluster config and falls back to the local kubeconfig,
so any reachable cluster works. Keep the k3d path as the front door in docs, and
keep cluster-specific detail out of the services.

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

### Container Images
Both Dockerfiles copy the whole `services/` tree and invoke the full module path (`python -m services.mcp_k8s_server.app.server`), matching local development. Do not copy a single service's `app/` directory to `/app/app`: `server.py` imports `services.mcp_k8s_server.app.k8s_client`, which is then unresolvable. Keep both images on the same convention.

---

## Known Issues

- **`k8s_client.list_pods` waiting-reason precedence is last-wins.** With several containers waiting, the loop overwrites `reason` each iteration, so the last container's reason survives. Arbitrary rather than wrong, but worth a decision if multi-container pods become common.
- **Unknown tool names abort the turn.** `run_turn()` raises `RuntimeError` on a tool name the server does not expose, while `call_tool` returns tool errors as strings for the model to recover from. Feeding the error back as a tool result would be consistent and let the model self-correct.
- **`scripts/run_tests.sh` treats exit code 4 as success.** Code 4 is a collection error, not an empty directory. It will hide a genuine import failure in a test module. Now that both service test directories have tests, the 4/5 special-casing can probably go.
- **`services/agent_chatbot/tests/` has no tests.** `tool_to_dict` and the `run_turn` loop are both untested.
- **`.DS_Store` is committed** at the repo root and in `deploy/`. Wants a `git rm --cached` and a `.gitignore` entry.
- **`chaosmesg-pod-failure-5m.yaml` is misspelled** (`chaosmesg`), as is the `deploy/chaosmesh` sibling naming otherwise.

---

## Workflow Preferences

- Do not commit by default. Make code changes and stop. The user reviews `git diff` before deciding to commit. Only commit when explicitly asked.
- Work lands on a feature branch and reaches `main` through a GitHub PR, not a local merge. `mcp_even_more_tools` was merged in PR #6 and deleted; create a new feature branch for the next unit of work.
- The worktree `claude/gallant-turing` should be resynced to the current feature branch (or `origin/main` if there is none) at the start of a session: `git reset --hard <ref>`.
- **Check for divergence before starting work.** The user commits in the main checkout while sessions are running, so the worktree goes stale mid-session. Run `git rev-list --left-right --count <branch>...HEAD` before committing, and rebase rather than merging.
- When committing, always use the `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` trailer.
- The user uses PyCharm (`.idea/` present) and ruff for linting.
- Avoid the use of emojis and em-dashes in any veribage or documentation created
- Avoid sycophancy in suggestions. Challenge me and suggest better ways of doing things.

---

## Planned Features

See `ideas.md` for the broader roadmap scratchpad.

1. **`get_events` tool** — Kubernetes events are often the first place to look when troubleshooting. RBAC already grants `events`, so no ClusterRole change is needed.
2. **FastAPI alerting webhook** — stateless endpoint that accepts alert payloads (Prometheus/Alertmanager format), runs the agent, returns structured diagnosis. Persistent MCP client via FastAPI lifespan, asyncio.Lock for concurrent request safety.
3. **Agentic loop safety** — consider a max iterations guard on the `while True` loop in `run_turn()`
4. **MCP `2026-07-28` migration** — pinned to `fastmcp>=3.0.2` speaking protocol `2025-11-25`; current is fastmcp 4.x speaking `2026-07-28`. The new revision removes sessions and the `initialize` handshake, none of which this server uses, and FastMCP 4 serves both protocol eras from one server. Do this after test coverage exists, not before. Note it also simplifies the webhook above: with no protocol session, the `asyncio.Lock` loses its transport-layer justification.
5. **Transport security** — the MCP endpoint is plaintext HTTP with no authentication, and compose publishes `8000:8000`. Acceptable on loopback against a throwaway cluster only. In-cluster needs TLS plus a bearer token or mTLS, and a NetworkPolicy.
6. **Model choice** — `MODEL` is hardcoded in `agent.py` and duplicated in the Makefile's `ollama pull`. Move it to an env var before benchmarking alternatives (Qwen3, MoE variants) so a swap does not require a code edit.

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
