# Ops Diagnostics Orchestrator

Hierarchical agent for diagnosing issues across multiple services using specialized subagents.

## Architecture

```
orchestrator.py              # Main CLI + orch_env (module-level)
├── environments/
│   ├── sentry.py            # Error monitoring (Sentry MCP)
│   ├── supabase.py          # Database/auth (Supabase MCP)
│   ├── railway.py           # Deployments (Railway MCP)
│   ├── kubectl.py           # Kubernetes (custom tools)
│   ├── docs.py              # Internal documentation (any Docs MCP)
│   └── github.py            # Code/issues/PRs (GitHub MCP)
├── tasks.json               # Eval tasks for subagents
└── run_evals.py             # Run evaluations
```

## Dynamic Subagent Detection

Subagents are **automatically registered** based on which environment variables are set. Only subagents with valid credentials will be available to the orchestrator.

| Subagent | Required Env Var(s) | Description |
|----------|---------------------|-------------|
| `investigate_sentry` | `SENTRY_AUTH_TOKEN` | Error monitoring |
| `investigate_supabase` | `SUPABASE_ACCESS_TOKEN` | Database/auth |
| `investigate_railway` | `RAILWAY_API_TOKEN` | Deployments |
| `investigate_kubernetes` | `KUBECONFIG_B64` or `KUBECONFIG` | Kubernetes cluster |
| `search_docs` | `DOCS_MCP` | Internal documentation |
| `investigate_github` | `GITHUB_PAT` | Code/issues/PRs |

This means you can run the orchestrator with just the services you have credentials for.

## Taiga

Requires `SENTRY_AUTH_TOKEN` baked into the image. Get one at https://sentry.io/settings/account/api/auth-tokens/

```bash
docker build --platform linux/amd64 --build-arg SENTRY_AUTH_TOKEN=sntrys_YOUR_TOKEN -t us-east1-docker.pkg.dev/gcp-taiga/hud/mario_ops_demo:0.07 . && docker push us-east1-docker.pkg.dev/gcp-taiga/hud/mario_ops_demo:0.07 && python generate_problems_metadata.py --image us-east1-docker.pkg.dev/gcp-taiga/hud/mario_ops_demo:0.07 --output taiga.json
```

## Docker Modes

The container supports two runtime modes via the `AGENT_MODE` environment variable:

| Mode | Command | Description |
|------|---------|-------------|
| `sentry` (default) | `hud dev environments.sentry:sentry_env` | Single Sentry subagent |
| `orch` | `hud dev orchestrator:orch_env` | Orchestrator with auto-detected subagents |

### Run in Sentry mode (default)
```bash
docker run -e SENTRY_AUTH_TOKEN=... hud-ops-diagnostics
```

### Run in Orchestrator mode
```bash
docker run -e AGENT_MODE=orch -e SENTRY_AUTH_TOKEN=... -e SUPABASE_ACCESS_TOKEN=... hud-ops-diagnostics
```

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure credentials

Create `.env` with your tokens. Only include the services you want to use:

```bash
# Sentry - https://sentry.io/settings/account/api/auth-tokens/
SENTRY_AUTH_TOKEN=sntrys_...

# Supabase - https://supabase.com/dashboard/account/tokens
SUPABASE_ACCESS_TOKEN=sbp_...
SUPABASE_PROJECT_REF=your_project_ref  # optional, scopes to specific project

# Railway - https://railway.app/account/tokens
RAILWAY_API_TOKEN=...

# GitHub - https://github.com/settings/tokens
GITHUB_PAT=ghp_...

# kubectl - base64 encoded kubeconfig
KUBECONFIG_B64=...

# Internal documentation MCP server URL
DOCS_MCP=https://docs.example.com/mcp

# OpenAI (for agents and Sentry AI-powered search)
OPENAI_API_KEY=sk-...
```

**Note:** Subagents are auto-detected based on which env vars are set. You don't need all of them.

### 3. Test connections

```bash
python orchestrator.py --test
```

Run with actual queries through each subagent:

```bash
python orchestrator.py --test --run-queries
```

## Usage

### Diagnose an issue

```bash
python orchestrator.py "Users report 500 errors on login"
```

### Incident response

```bash
python orchestrator.py --incident "Production is down" --severity critical
```

### Use a different model

```bash
python orchestrator.py "Slow queries" --model gpt-4o
```

## How it works

1. **Orchestrator** receives your query
2. Decides which **subagents** to call based on the issue
3. Each subagent uses its specialized MCP tools (Sentry, Supabase, etc.)
4. Orchestrator correlates findings and provides diagnosis

### Architecture Pattern

Each subagent is a HUD Environment with:
- MCP server connection (real tools)
- A v5 scenario for investigation queries
- Optional eval-only parameters for scoring

```python
@sentry_env.scenario("investigate")
async def investigate_issue(query: str, must_include: list[str] | None = None):
    prompt = f"Investigate: {query}"
    response = yield prompt
    # Score based on must_include
    yield score
```

### Benefits

- **Up to 6 subagents** instead of 60+ tools (reduced cognitive load)
- **Specialized agents** for each domain (Sentry, Supabase, Railway, kubectl, Docs, GitHub)
- **Auto-detected** based on which env vars are present
- **Testable** - each subagent runs independently
- **Composable** - easy to add/remove services
- **READ-ONLY** - subagents investigate but don't make changes

## Running Evaluations

The `tasks.json` file contains evaluation tasks for the Sentry subagent:

```bash
# Run all tasks
python run_evals.py

# Run specific task
python run_evals.py --task find_responses_schema_error
```

Tasks test that agents can:
- Find specific errors by type
- Navigate complex Sentry data
- Avoid common confusion (e.g., similar issue IDs)

## Testing individual subagents

```bash
python environments/sentry.py
python environments/supabase.py
python environments/railway.py
python environments/kubectl.py
python environments/docs.py
python environments/github.py
```

## Available Subagents

### Sentry (`investigate_sentry`)
Error monitoring and issue investigation.
- `search_issues` - Find issues by query
- `get_issue_details` - Full issue details
- `analyze_issue_with_seer` - AI root cause analysis
- `find_organizations`, `find_projects`, etc.

### Supabase (`investigate_supabase`)
Database and auth investigation.
- `list_tables`, `execute_sql`
- `get_logs`, `get_advisors`
- `list_edge_functions`, etc.

### Railway (`investigate_railway`)
Deployment status and logs.
- `list-projects`, `list-services`
- `list-deployments`, `get-logs`
- `deploy`, etc.

### kubectl (`investigate_kubernetes`)
Kubernetes cluster health.
- `kubectl_get_pods`, `kubectl_get_logs`
- `kubectl_describe_pod`, `kubectl_get_events`, etc.

### Internal Docs (`search_docs`)
Internal documentation search (configurable via `DOCS_MCP`).
- Search docs for architecture, concepts, examples
- Connect to any docs MCP server via URL
- Set `DOCS_MCP=https://docs.example.com/mcp`

### GitHub (`investigate_github`)
Code, issues, PRs, and workflows.
- Search code across repositories
- Get issues and pull requests
- Check GitHub Actions workflow runs
- Repository and file browsing
