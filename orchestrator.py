#!/usr/bin/env python3
"""Ops Diagnostics Orchestrator - CLI for investigating issues across services.

Usage:
    python orchestrator.py "Users report 500 errors on login"
    python orchestrator.py "Database connection timeouts" --services supabase,railway
    python orchestrator.py --incident "Production is down" --severity critical
"""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any

# Fix Windows console encoding for Unicode
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from rich.console import Console
from rich.errors import MarkupError
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

load_dotenv()

# Configure logging to stderr so it doesn't interfere with rich output
logging.basicConfig(
    stream=sys.stderr,
    level=logging.WARNING,
    format="[%(levelname)s] %(name)s | %(message)s",
)

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

console = Console(force_terminal=True, legacy_windows=False)

# =============================================================================
# ORCHESTRATOR ENVIRONMENT (module-level for hud dev)
# =============================================================================

from hud import Environment
from hud.tools import AgentTool

orch_env = Environment(name="ops-orchestrator")

# Get model from env or default
_orch_model = os.getenv("ORCH_MODEL", "gpt-4o-mini")

# Define subagents with their required env vars
# Format: (tool_name, module_attr, description, required_env_vars)
# required_env_vars: list of env var names - ANY of them must be present (OR logic)
#                    None means always available (no env var required)
_subagent_configs: list[tuple[str, str, str, list[str] | None]] = [
    ("investigate_sentry", "sentry_env", "Investigate errors in Sentry", ["SENTRY_AUTH_TOKEN"]),
    ("investigate_supabase", "supabase_env", "Investigate database/auth in Supabase", ["SUPABASE_ACCESS_TOKEN"]),
    ("investigate_railway", "railway_env", "Investigate deployments in Railway", ["RAILWAY_API_TOKEN"]),
    ("investigate_kubernetes", "kubectl_env", "Investigate Kubernetes cluster", ["KUBECONFIG_B64", "KUBECONFIG"]),
    ("search_docs", "docs_env", "Search internal documentation for architecture, concepts, and guides", ["DOCS_MCP"]),
    ("investigate_github", "github_env", "Search code, issues, PRs, and workflows on GitHub", ["GITHUB_PAT"]),
]

# Build list of available subagents based on env vars
_subagents: list[tuple[str, Environment, str]] = []
_logger = logging.getLogger(__name__)

for _name, _module_attr, _desc, _required_vars in _subagent_configs:
    # Check if required env vars are present
    if _required_vars is not None:
        # Check if ANY of the required vars are set (OR logic)
        has_env_var = any(os.getenv(var) for var in _required_vars)
        if not has_env_var:
            _logger.info("Skipping %s - missing env var(s): %s", _name, _required_vars)
            continue
    
    # Import the environment lazily (only if env vars are present)
    import environments
    _env = getattr(environments, _module_attr)
    _subagents.append((_name, _env, _desc))
    _logger.info("Registered subagent: %s", _name)

# Add the available subagent tools to the orchestrator
for _name, _env, _desc in _subagents:
    _tool = AgentTool(
        _env("investigate"),
        model=_orch_model,
        name=_name,
        description=_desc,
    )
    orch_env.add_tool(_tool.mcp)


def _format_subagent_list(detailed: bool = True) -> str:
    """Format the list of available subagents for prompts."""
    if not _subagents:
        return "No subagents available."
    
    if detailed:
        return "\n".join(f"- **{name}**: {desc}" for name, _, desc in _subagents)
    else:
        return "\n".join(f"- {name}: {desc}" for name, _, desc in _subagents)


@orch_env.scenario("diagnose")
async def orch_diagnose(query: str) -> Any:
    """Diagnose an ops issue using specialized subagents.
    
    Args:
        query: The issue to diagnose (e.g., "Users report 500 errors on login")
    """
    subagent_list = _format_subagent_list(detailed=True)
    
    system_prompt = f"""You are an ops diagnostics orchestrator with specialized subagents:

{subagent_list}

**Issue to diagnose:**
{query}

**IMPORTANT: All subagents are READ-ONLY. They investigate but do NOT make changes.**

**Instructions:**
1. Use the appropriate subagent tools to investigate
2. Each tool takes a "query" parameter - describe what to look for
3. Correlate findings across services
4. If you need to understand expected behavior, use search_docs
5. If you need to check source code or recent changes, use investigate_github
6. Provide a comprehensive diagnosis with recommended actions for humans to take

Be systematic. Call multiple subagents if needed."""
    
    response = yield system_prompt
    yield 1.0 if response else 0.0


@orch_env.scenario("incident")
async def orch_incident(desc: str, sev: str = "high") -> Any:
    """Handle an incident using specialized subagents.
    
    Args:
        desc: Description of the incident
        sev: Severity level (low, medium, high, critical)
    """
    subagent_list = _format_subagent_list(detailed=False)
    
    prompt = f"""*** INCIDENT RESPONSE (READ-ONLY INVESTIGATION) ***

**Severity:** {sev.upper()}
**Description:** {desc}

You have specialized READ-ONLY subagents:
{subagent_list}

**Priority actions:**
1. Quickly assess scope
2. Identify root cause (use search_docs to understand expected behavior if needed)
3. Check recent code changes with investigate_github if deployment-related
4. Suggest immediate mitigation (for humans to execute)
5. Document findings

Note: You cannot make changes. Provide actionable recommendations.
Time is critical. Be concise."""
    
    response = yield prompt
    yield 1.0 if response else 0.0


# =============================================================================
# CLI FUNCTIONS
# =============================================================================

def print_header():
    console.print()
    console.print(Panel.fit(
        "[bold blue]Ops Diagnostics Orchestrator[/bold blue]\n"
        "[dim]Hierarchical agent with specialized subagents[/dim]",
        border_style="blue"
    ))
    console.print()


async def run_diagnosis(prompt: str, model: str = "gpt-4o-mini"):
    """Run the orchestrator with the given prompt."""
    from hud.agents import create_agent
    import hud
    
    console.print("[dim]Using module-level orchestrator with subagents...[/dim]")
    for name, _, _ in _subagents:
        console.print(f"  [green]+[/green] {name}")
    console.print()
    
    # Create task using module-level orch_env
    task = orch_env("diagnose", query=prompt)
    
    # Run with agent
    console.print(Panel(prompt, title="[bold]Query[/bold]", border_style="yellow"))
    console.print()
    
    with console.status("[bold green]Orchestrator thinking...", spinner="dots"):
        async with hud.eval(task) as ctx:
            agent = create_agent(model)
            try:
                result = await agent.run(ctx, max_steps=20)
            except MarkupError as e:
                # Workaround for Rich markup errors from SDK error handling
                console.print(f"\n[red]Agent error (markup issue): {e!r}[/red]")
                result = type("Result", (), {"content": None})()
            except Exception as e:
                # Catch any other error and display safely
                console.print(f"\n[red]Agent error: {type(e).__name__}: {e!s}[/red]")
                result = type("Result", (), {"content": None})()
    
    # Display result
    console.print()
    if result.content:
        console.print(Panel(
            Markdown(result.content),
            title="[bold green]Diagnosis[/bold green]",
            border_style="green"
        ))
    else:
        console.print("[red]No response from agent[/red]")
    
    return result


async def run_incident(description: str, severity: str, model: str):
    """Run incident response mode."""
    from hud.agents import create_agent
    import hud
    
    console.print("[dim]Using module-level orchestrator for incident response...[/dim]")
    for name, _, _ in _subagents:
        console.print(f"  [green]+[/green] {name}")
    console.print()
    
    # Create task using module-level orch_env
    task = orch_env("incident", desc=description, sev=severity)
    
    severity_colors = {"critical": "red", "high": "yellow", "medium": "blue", "low": "dim"}
    color = severity_colors.get(severity.lower(), "white")
    
    console.print(Panel(
        f"[bold {color}]{severity.upper()}[/bold {color}]\n\n{description}",
        title="[bold red]INCIDENT[/bold red]",
        border_style="red"
    ))
    console.print()
    
    with console.status("[bold red]Incident response in progress...", spinner="dots"):
        async with hud.eval(task) as ctx:
            agent = create_agent(model)
            try:
                result = await agent.run(ctx, max_steps=20)
            except MarkupError as e:
                console.print(f"\n[red]Agent error (markup issue): {e!r}[/red]")
                result = type("Result", (), {"content": None})()
            except Exception as e:
                console.print(f"\n[red]Agent error: {type(e).__name__}: {e!s}[/red]")
                result = type("Result", (), {"content": None})()
    
    console.print()
    if result.content:
        console.print(Panel(
            Markdown(result.content),
            title="[bold]Incident Report[/bold]",
            border_style="red"
        ))
    
    return result


async def test_subagents(run_queries: bool = False, model: str = "gpt-4o-mini"):
    """Test that all available subagents can connect and optionally run queries."""
    from hud.tools import AgentTool
    
    # Test queries for each subagent type
    test_queries = {
        "investigate_sentry": "List recent errors or issues",
        "investigate_supabase": "List database tables",
        "investigate_railway": "List projects and their status",
        "investigate_kubernetes": "List nodes in the cluster",
        "search_docs": "How do I get started?",
        "investigate_github": "Search for recent commits",
    }
    
    if not _subagents:
        console.print("[yellow]No subagents available - check environment variables[/yellow]")
        console.print("\nRequired env vars:")
        for name, _, _, req_vars in _subagent_configs:
            if req_vars:
                console.print(f"  {name}: {' or '.join(req_vars)}")
            else:
                console.print(f"  {name}: (no env var required)")
        return
    
    console.print("[bold]Testing available subagent connections...[/bold]\n")
    
    for name, env, _ in _subagents:
        try:
            async with env:
                tools = env.as_tools()
                console.print(f"  [green]+[/green] {name}: {len(tools)} tools")
        except Exception as e:
            console.print(f"  [red]x[/red] {name}: {e}")
    
    console.print()
    
    if run_queries:
        console.print("[bold]Running test queries through each subagent...[/bold]\n")
        
        for name, env, _ in _subagents:
            query = test_queries.get(name, "Describe your capabilities")
            console.print(Panel(f"[bold]{name}[/bold]: {query}", border_style="cyan"))
            
            try:
                # Create AgentTool for this environment's investigate scenario
                tool = AgentTool(
                    env("investigate"),
                    model=model,
                    name=f"test_{name}",
                )
                
                # Run it
                with console.status(f"[cyan]{name} agent working..."):
                    result = await tool(query=query)
                
                # Show result
                if result.content:
                    text = result.content[0].text if result.content else "No response"
                    console.print(Panel(
                        Markdown(text[:1500] + "..." if len(text) > 1500 else text),
                        title=f"[green]{name} Response[/green]",
                        border_style="green"
                    ))
                else:
                    console.print(f"  [yellow]No response from {name}[/yellow]")
                    
            except Exception as e:
                console.print(f"  [red]x[/red] {name} query failed: {e}")
            
            console.print()


def main():
    parser = argparse.ArgumentParser(
        description="Ops Diagnostics Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python orchestrator.py "Users report 500 errors on login"
  python orchestrator.py "Database is slow" --model gpt-4o
  python orchestrator.py --incident "Production is down" --severity critical
  python orchestrator.py --test
        """
    )
    
    parser.add_argument(
        "query",
        nargs="?",
        help="Issue to diagnose"
    )
    parser.add_argument(
        "--incident",
        metavar="DESC",
        help="Run in incident response mode"
    )
    parser.add_argument(
        "--severity",
        choices=["low", "medium", "high", "critical"],
        default="high",
        help="Incident severity (default: high)"
    )
    parser.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="Model to use (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test subagent connections"
    )
    parser.add_argument(
        "--run-queries",
        action="store_true",
        help="Run test queries through each subagent (use with --test)"
    )
    
    args = parser.parse_args()
    
    print_header()
    
    if args.test:
        asyncio.run(test_subagents(run_queries=args.run_queries, model=args.model))
    elif args.incident:
        asyncio.run(run_incident(args.incident, args.severity, args.model))
    elif args.query:
        asyncio.run(run_diagnosis(args.query, args.model))
    else:
        parser.print_help()
        console.print("\n[dim]Tip: Pass a query to diagnose, e.g.:[/dim]")
        console.print('  python orchestrator.py "Users getting 500 errors"\n')


if __name__ == "__main__":
    main()
