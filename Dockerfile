# Ops Diagnostics - Taiga Dockerfile
#
# Build:
#   docker build --platform linux/amd64 \
#     --build-arg SENTRY_AUTH_TOKEN=sntrys_... \
#     -t us-east1-docker.pkg.dev/gcp-taiga/hud/ops_diagnostics:0.01 .
#
# The MCP server exposes Sentry tools + setup_problem + grade_problem.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    git \
    && rm -rf /var/lib/apt/lists/*

# Node.js for npx @sentry/mcp-server
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies system-wide (not in venv) so python3 can find them
COPY pyproject.toml ./
RUN uv pip install --system --break-system-packages -e .

# Pre-install Sentry MCP server
RUN npm install -g @sentry/mcp-server@latest || true

# Copy source
COPY environments/ ./environments/
COPY tasks.yaml ./
COPY start.sh ./
RUN chmod +x /app/start.sh

# Environment
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED="1"
ENV IS_TAIGA="1"

# REQUIRED: pass your real Sentry token at build time.
# Without it, the Sentry MCP server won't start and the agent has no tools.
# docker build --build-arg SENTRY_AUTH_TOKEN=sntrys_... ...
ARG SENTRY_AUTH_TOKEN=""
ENV SENTRY_AUTH_TOKEN=$SENTRY_AUTH_TOKEN

CMD ["/app/start.sh"]
