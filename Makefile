VERSION := 0.1.0

.PHONY: ollama server agent start lint format test

## ── Local development ────────────────────────────────────────────────────────

# Pull the LLM model if not already cached, then start the Ollama server.
# Run this in a separate terminal before starting the agent.
ollama:
	ollama pull llama3.1:8b
	ollama serve

# Start the MCP k8s server.
server:
	uv run python -m services.mcp_k8s_server.app.server

# Start the interactive agent chatbot.
# Requires the MCP server to already be running.
agent:
	uv run python -m services.agent_chatbot.app.agent

# Start both the MCP server (background) and agent (foreground).
# The server is killed automatically when the agent exits or Ctrl+C is pressed.
start:
	@uv run python -m services.mcp_k8s_server.app.server & \
	SERVER_PID=$$!; \
	trap "kill $$SERVER_PID" EXIT; \
	uv run python -m services.agent_chatbot.app.agent

## ── Code quality ─────────────────────────────────────────────────────────────

# Check for lint errors with ruff.
lint:
	uv run ruff check .

# Reformat code with ruff.
format:
	uv run ruff format .

## ── Tests ────────────────────────────────────────────────────────────────────

# Run pytest against both service test directories.
test:
	uv run pytest services/mcp_k8s_server/tests services/agent_chatbot/tests -v
