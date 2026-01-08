# Ops Diagnostics Orchestrator

Hierarchical agent for diagnosing issues across multiple services using specialized subagents.

## Architecture

```
orchestrator.py          # Main CLI - coordinates subagents
├── agents/
│   ├── sentry_agent.py      # Error monitoring (Sentry MCP)
│   ├── supabase_agent.py    # Database/auth (Supabase MCP)
│   ├── railway_agent.py     # Deployments (Railway MCP)
│   └── kubectl_agent.py     # Kubernetes (custom tools)
└── tools/
    └── kubectl.py           # kubectl CLI wrappers
```

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure credentials

Create `.env` with your tokens:

```bash
# Sentry - https://sentry.io/settings/account/api/auth-tokens/
SENTRY_AUTH_TOKEN=sntrys_...

# Supabase - https://supabase.com/dashboard/account/tokens
SUPABASE_ACCESS_TOKEN=sbp_...
SUPABASE_PROJECT_REF=your_project_ref

# Railway - https://railway.app/account/tokens
RAILWAY_API_TOKEN=...

# kubectl - base64 encoded kubeconfig
KUBECONFIG_BASE64=...
```

### 3. Test connections

```bash
python orchestrator.py --test
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
3. Each subagent uses its specialized tools (Sentry, Supabase, etc.)
4. Orchestrator correlates findings and provides diagnosis

### Benefits

- **4 tools** instead of 60+ (reduced cognitive load)
- **Specialized agents** for each domain
- **Testable** - each subagent runs independently
- **Composable** - easy to add/remove services

## Testing individual subagents

```bash
python agents/sentry_agent.py
python agents/supabase_agent.py
python agents/railway_agent.py
python agents/kubectl_agent.py
```

## Available Tools (per subagent)

### Sentry (via MCP)
`whoami`, `find_organizations`, `find_projects`, `search_issues`, `get_issue_details`, `analyze_issue_with_seer`, ...

### Supabase (via MCP)
`list_tables`, `execute_sql`, `get_logs`, `get_advisors`, `list_edge_functions`, ...

### Railway (via MCP)
`list-projects`, `list-services`, `list-deployments`, `get-logs`, `deploy`, ...

### kubectl (custom)
`kubectl_get_pods`, `kubectl_get_logs`, `kubectl_describe_pod`, `kubectl_get_events`, ...
