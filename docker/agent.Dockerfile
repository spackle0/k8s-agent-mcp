FROM python:3.14-slim

WORKDIR /app

COPY services/agent_chatbot/app /app/app
COPY pyproject.toml /app/

RUN pip install --no-cache-dir .

# MCP_SERVER_URL can be overridden at runtime to point to the server container.
ENV MCP_SERVER_URL=http://mcp-server:8000/mcp

CMD ["python", "-m", "app.agent"]
