FROM python:3.14-slim

WORKDIR /app

# Copy the whole services tree rather than just this service's app directory.
# server.py imports `services.mcp_k8s_server.app.k8s_client`, so the package
# path has to match the one used in local development. Copying only
# `app/` leaves that import unresolvable inside the image.
COPY pyproject.toml /app/
COPY services /app/services

RUN pip install --no-cache-dir .

CMD ["python", "-m", "services.mcp_k8s_server.app.server"]
