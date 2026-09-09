# Blog series outline: Building a Kubernetes troubleshooting agent

Working title for the series: **Ask Your Cluster What Is Wrong**

## Positioning

The crowded version of this post is "I hooked an LLM up to kubectl." The
differentiated version is the part almost nobody writes about: the trust
boundary, what happens when the model is wrong, and how you prove the thing
actually works. Lead with the engineering, not the demo.

Two things this series has that most do not:

1. **Chaos Mesh as a test harness.** Real, reproducible failures the agent has to
   diagnose. Everyone else screenshots a happy path. You can show the agent
   failing, then show it succeeding after a fix.
2. **A read-only RBAC boundary designed in from the start**, not bolted on in a
   "security considerations" paragraph at the end.

Audience: platform and SRE engineers who are LLM-curious but skeptical. Assume
Kubernetes fluency, assume nothing about MCP.

The honest framing that will earn trust: this is not a replacement for knowing
your cluster. It compresses the first ten minutes of triage. Say that out loud in
post 1, because readers in this audience are allergic to overclaiming and will
stop reading the moment they smell it.

---

## Post 1: Why an agent, and why not just kubectl

**The hook.** Open with a concrete triage session. Pod is unhealthy. You run
`get pods`, then `describe`, then `logs`, then `get events`, then `logs
--previous`. Five commands, four of them predictable from the output of the
previous one. That predictable chain is the thing worth automating, and it is
worth automating precisely because it is boring, not because it is hard.

**What to cover**
- The difference between a natural-language kubectl wrapper and an agent. The
  wrapper translates one sentence into one command. The agent decides what to
  look at next based on what it just saw. Chained tool calls are the whole point.
- Why local inference. Cluster state, pod logs, and namespace names are not
  things most people want to ship to a third-party API. This constraint shapes
  everything downstream, including model choice.
- Why MCP rather than hand-rolled function calling. Tool definitions live with
  the thing that implements them, and any MCP client can use the server.
- Scope discipline: read-only, diagnosis only, no remediation. State the reason.
  A model that can restart a deployment is a model that can restart the wrong
  deployment at 3am.

**Ends with** the architecture diagram and an honest statement of what the thing
does not do.

---

## Post 2: An MCP server over the Kubernetes API

**The hook.** The smallest useful MCP server is about forty lines, and the
interesting decisions are all in what you choose not to build.

**What to cover**
- FastMCP standalone, `@mcp.tool()`, streamable-HTTP transport. Note the import
  gotcha: `from fastmcp import FastMCP`, not `mcp.server.fastmcp`.
- **Serialization is the first wall you hit.** `V1Pod` is not JSON-serializable.
  Show the failure, then the fix: extract named fields into plain dicts in the
  client wrapper so tools stay thin. This is a genuinely useful thing to have
  written down; people hit it immediately.
- **Docstrings are prompt engineering.** The docstring is sent to the model as
  the tool definition. Show a vague one and the resulting hallucinated argument,
  then the explicit one that documents every return field. Concrete before/after
  is the most valuable half-page in the series.
- **Tool granularity, argued properly.** The temptation is
  `get_crashlooping_pods`. Resist it. Return enough from `list_pods` for the
  model to work it out. The rule: a new tool earns its place when it needs a
  different API call, not when it is a filter over data you already have.
  Narrow tools push your judgment into the tool surface and make the model worse
  at situations you did not anticipate.
- In-cluster config with kubeconfig fallback, so one image runs in both places.

**Code to show**: `server.py` in full, `k8s_client.list_pods` extraction.

---

## Post 3: The agentic loop

**The hook.** The loop is about twenty lines. Everything hard about it is in the
failure modes.

**What to cover**
- Turn structure: call model, execute requested tools, append results, repeat
  until the model stops asking for tools.
- The MCP-to-Ollama tool schema adapter. Same information, different shape.
- Extracting `result.content[0].text` before handing it back to the model.
- Persistent client and message history across turns, and why you build the
  Ollama tool list once at startup.
- **`while True` is a bug waiting for a bad model.** An 8B model will loop,
  calling `list_namespaces` five times in a row. Show it happening. Then add the
  iteration cap and explain what the model should be told when it hits the cap.
- **Two philosophies of error handling in one file.** A tool that errors returns
  a string the model can recover from. A tool name that does not exist raises and
  kills the turn. Walk through why the recoverable path is almost always right:
  the model reads the error, apologizes, and tries the correct name. Handing
  errors back to the model as data is the single highest-leverage reliability
  trick in agent work.
- Context growth. Pod logs are large, history is unbounded, and the context
  window is the real budget you are spending.

---

## Post 4: Giving it something real to break

**This is the post that separates the series from the pack.** Most write-ups
demonstrate on a healthy cluster, which proves nothing.

**What to cover**
- Chaos Mesh setup and the three experiments: pod-kill on a cron, CPU stress,
  network latency. Bounded durations, reversible, declarative.
- Blackbox exporter and the Probe CR, so injected latency is visible as
  `probe_duration_seconds` rather than a claim.
- **Run the agent against each failure and publish what it actually said.**
  Including the failures. The pod-kill case is easy and it will nail it. The
  latency case it will probably miss, because `list_pods` and `read_pod_log`
  cannot see network latency at all. That miss is the most instructive moment in
  the entire series: the agent's ceiling is its tool surface, not its model.
- Which leads directly to: what tool would fix that? `get_events` first, because
  events are where Kubernetes writes down what it noticed. Then metrics.
- A note on evaluation. Once you have reproducible failures, you have a
  regression suite. Change the model or a docstring, rerun the experiments,
  compare. Gesture at this even if you have not built it, because it is the
  correct destination and readers will respect that you know it.

---

## Post 5: The trust boundary

**The hook.** The agent has no cluster credentials. It cannot, by construction,
do anything to your cluster. Here is how that is arranged and where it is still
thin.

**What to cover**
- The two-process split as a security property, not an architecture aesthetic.
  Only the MCP server holds credentials, and it exposes a fixed vocabulary.
- The read-only ClusterRole, verb by verb. No write verbs anywhere. Why
  `pods/log` is separate and worth thinking about, because logs routinely contain
  secrets that pod specs do not.
- **Running with your own kubeconfig gives the agent your permissions**, which
  are almost certainly cluster-admin. Fine on a laptop against a homelab,
  actively dangerous anywhere else. Say this plainly.
- The gap: plaintext HTTP, no authentication on the MCP endpoint. Loopback-only
  is a real mitigation and worth naming as one, but the moment the server moves
  into the cluster it needs TLS and a bearer token or mTLS.
- **Prompt injection is not hypothetical here.** Pod logs are attacker-influenced
  data. Anything that can write to a log can write text addressed to your agent.
  With read-only tools the worst case is a wrong answer, which is exactly why
  read-only is load-bearing rather than a nice-to-have. Spell out what changes
  the day someone adds a write tool.
- Practical hardening list: network policy on the MCP service, per-namespace
  RoleBindings instead of a ClusterRole, log redaction, audit logging of tool
  calls.

**This is likely the most-linked post in the series.** Almost nobody writes it.

---

## Post 6: Model choice and protocol churn

**The hook.** Two moving parts underneath you: the model and the protocol. Both
changed while this was being written. Here is what actually broke.

**What to cover**
- Swapping the model. In this design it is one constant, because Ollama
  normalizes tool calling into a single response shape. What genuinely differs:
  context window, tool-call formatting reliability, and how chatty the model is
  inside the loop, which is a cost and latency question more than a correctness
  one.
- How to evaluate a model swap honestly: rerun the chaos experiments, count
  well-formed tool calls, count iterations per turn. Not vibes.
- Hardware reality. A homelab box constrains model size, and model size
  constrains how much context you can spend on pod logs. This is the actual
  binding constraint in a self-hosted setup, and nobody writes about it.
- MCP protocol churn. `2026-07-28` removed sessions and the initialize
  handshake, made requests self-contained, and added `server/discover`. Why
  stateless is the right call for HTTP-transported tools, and why a
  three-tool read-only server is nearly unaffected by a change that sounds
  enormous.
- The general lesson: pin your versions, read changelogs, and prefer a design
  where the framework absorbs protocol changes for you.

---

## Post 7 (optional): From chatbot to webhook

Only worth writing once the FastAPI alerting endpoint exists.

**What to cover**
- Alertmanager fires, the agent diagnoses, the diagnosis arrives attached to the
  alert. This is the payoff the whole series has been building toward: nobody
  actually wants to chat with their cluster, they want the triage already done
  when they open the page.
- Persistent MCP client via FastAPI lifespan.
- Concurrency. The message history in the interactive agent is per-session state
  and a webhook is not a session. Build the history per request.
- Structured output so the diagnosis is a field, not a paragraph.
- Where a human stays in the loop, and why that is not a temporary limitation.

---

## Production notes

**Order and cadence.** Posts 1 to 3 are a coherent unit and can ship close
together. Post 4 is the one to promote hardest. Post 5 is the one that gets
linked in other people's posts six months later.

**Per post**: one diagram, real terminal output rather than idealized output, and
a link to the tagged commit the post describes. Tag the repo per post so readers
can check out the exact state. This is worth the small amount of effort and
almost nobody does it.

**Publish the failures.** The latency miss in post 4, the model looping in post 3,
the broken Dockerfile CMD if you want a fourth. Posts that only show things
working read as marketing and this audience discounts them accordingly.

**Recurring thread to keep explicit**: the agent's ceiling is its tool surface.
Every post should add one piece of evidence for that claim. It is the thesis, and
a series with a thesis beats a series of tutorials.
