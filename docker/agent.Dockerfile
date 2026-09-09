FROM python:3.14-slim

WORKDIR /app

# Same layout as the MCP server image: copy the whole services tree and use the
# full module path, so container and local development invocations match.
COPY pyproject.toml /app/
COPY services /app/services

RUN pip install --no-cache-dir .

# MCP_SERVER_URL can be overridden at runtime to point to the server container.
ENV MCP_SERVER_URL=http://mcp-server:8000/mcp

CMD ["python", "-m", "services.agent_chatbot.app.agent"]
