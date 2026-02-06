#!/bin/bash
# Startup script for both Taiga and HUD modes.
#
# IS_TAIGA is read by environments/sentry.py to conditionally register
# setup_problem and grade_problem tools. Uses env.run() directly
# (not hud dev) for proper MCP tool exposure on Taiga.

cd /app

export IS_TAIGA="${IS_TAIGA:-0}"

if [ "$AGENT_MODE" = "orch" ]; then
    exec python3 -m orchestrator
else
    exec python3 -m environments.sentry
fi
