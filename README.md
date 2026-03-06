# k8s-agent-mcp

![semver](https://img.shields.io/badge/semver-0.1.0-blue)

[![Python 3.14](https://img.shields.io/badge/python-3.14-blue.svg)](https://www.python.org/downloads/release/python-360/)

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)

[![CI](https://github.com/spackle0/k8s-agent-mcp/actions/workflows/docker-build-test.yaml/badge.svg)](https://github.com/spackle0/k8s-agent-mcp/actions/workflows/ci.yml)

[![codecov](https://codecov.io/gh/spackle0/k8s-agent-mcp/graph/badge.svg?token=YJVD7W9Q37)](https://codecov.io/gh/spackle0/k8s-agent-mcp)


An experiment in Agentic AI with a Kubernetes slant

## Docker Compose (interactive agent)

The `agent` service is interactive — the container keeps STDIN open and allocates a TTY so you can type directly into the running Python process.

Build and run the agent interactively (recommended):

```bash
# Build the agent image (optional; compose will build automatically if needed)
make compose-agent
# or run directly:
docker compose run --rm -it agent
```

If you prefer to run everything in the background and then open an interactive shell inside the agent container:

```bash
# Start services in background
docker compose up -d
# Open a shell in the agent container and run the agent interactively
docker compose exec -it agent /bin/sh
python -m app.agent
```

To attach to the main agent process (only when started with a TTY):

```bash
docker compose ps
docker attach <container-name-or-id>
# Detach without stopping: Ctrl-p Ctrl-q
```

The Makefile includes helpers `make compose-agent` and `make compose-up` that wrap the common commands.
