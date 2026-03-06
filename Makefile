VERSION := 0.1.0

.PHONY: help ollama server agent start lint format test compose-agent compose-up pre-commit-enable pre-commit-disable

help:
	@printf "k8s-agent-mcp Makefile help\n\n"
	@printf "Usage: make <target>\n\n"
	@printf "Common targets (run 'make <target>'):\n"
	@printf "  ollama        - Pulls the LLM model (ollama) and starts the Ollama server.\n"
	@printf "  server        - Starts the MCP k8s server (FastMCP) in the foreground.\n"
	@printf "  agent         - Runs the interactive agent chatbot locally (requires server).\n"
	@printf "  start         - Starts the MCP server in the background and runs the agent in the foreground.\n"
	@printf "  compose-agent - Build the agent image and run it interactively via Docker Compose.\n"
	@printf "  compose-up    - Start mcp-server and agent in detached mode via Docker Compose.\n"
	@printf "  lint               - Run ruff to check for lint issues.\n"
	@printf "  format             - Run ruff to autoformat code.\n"
	@printf "  test               - Run the project's pytest test suite for services.\n"
	@printf "  pre-commit-enable  - Install pre-commit hooks into .git/hooks.\n"
	@printf "  pre-commit-disable - Remove pre-commit hooks from .git/hooks.\n\n"
	@printf "Notes:\n"
	@printf "  - 'make' with no args shows this help (default).\n"
	@printf "  - Use 'make compose-agent' to run the agent interactively inside Docker.\n"
	@printf "  - Use 'docker compose up -d' + 'docker compose exec -it agent /bin/sh' to exec into a running agent.\n"
	@printf "\n"

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

# Convenience: run the agent via docker-compose interactively
compose-agent:
	docker compose build agent
	docker compose run --rm -it agent

# Convenience: bring up compose services in background (mcp-server + agent)
compose-up:
	docker compose up -d mcp-server agent

## ── Pre-commit ───────────────────────────────────────────────────────────────

# Install pre-commit hooks so they run automatically on every commit.
pre-commit-enable:
	pre-commit install

# Remove pre-commit hooks from .git/hooks.
pre-commit-disable:
	pre-commit uninstall

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
