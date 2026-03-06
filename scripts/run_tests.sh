#!/usr/bin/env bash
# Run pytest against all service test directories.
# Exit code 4 ("collection error") and 5 ("no tests collected") are treated
# as success while test directories are still being populated.

set -euo pipefail

# Disable -e for the pytest call to be able to inspect the exit code
set +e

# TODO: put the dirs in a list
uv run pytest services/mcp_k8s_server/tests services/agent_chatbot/tests -v
rc=$?
set -e # Set it back now

if [ $rc -eq 4 ] || [ $rc -eq 5 ]; then
    # This is for having empty dirs. Should probably nix this later.
    echo "No tests collected — treating as success."
    exit 0
fi

exit $rc
