#!/usr/bin/env bash
# Run pytest against all service test directories.
# Exit code 5 ("no tests collected") is treated as success so CI passes
# while test directories are still being populated.

set -euo pipefail

uv run pytest services/mcp_k8s_server/tests services/agent_chatbot/tests -v
code=$?

if [ $code -eq 5 ]; then
    echo "No tests collected — treating as success."
    exit 0
fi

exit $code
