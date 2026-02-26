FROM python:3.14-slim

WORKDIR /app

COPY services/mcp_k8s_server/app /app/app
COPY pyproject.toml /app/

RUN pip install --no-cache-dir fastapi uvicorn kubernetes pydantic

CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000"]