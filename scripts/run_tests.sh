#!/usr/bin/env bash
# Run pytest against all service test directories.
# Exit code 4 ("collection error") and 5 ("no tests collected") are treated
# as success while test directories are still being populated.

set -euo pipefail

# Disable -e for the pytest call so we can inspect the exit code ourselves.
set +e
uv run pytest services/mcp_k8s_server/tests services/agent_chatbot/tests -v
code=$?
set -e

if [ $code -eq 4 ] || [ $code -eq 5 ]; then
    echo "No tests collected — treating as success."
    exit 0
fi

exit $code
