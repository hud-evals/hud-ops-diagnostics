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

# Import subagent environments
from environments import sentry_env, supabase_env, railway_env, kubectl_env, hud_docs_env, github_env

orch_env = Environment(name="ops-orchestrator")

# Get model from env or default
_orch_model = os.getenv("ORCH_MODEL", "gpt-4o-mini")

# Add subagent tools
_subagents = [
    ("investigate_sentry", sentry_env, "Investigate errors in Sentry"),
    ("investigate_supabase", supabase_env, "Investigate database/auth in Supabase"),
    ("investigate_railway", railway_env, "Investigate deployments in Railway"),
    ("investigate_kubernetes", kubectl_env, "Investigate Kubernetes cluster"),
    ("search_hud_docs", hud_docs_env, "Search HUD documentation for architecture, v5 scenarios, SDK concepts"),
    ("investigate_github", github_env, "Search code, issues, PRs, and workflows on GitHub"),
]

for _name, _env, _desc in _subagents:
    _tool = AgentTool(
        _env("investigate"),
        model=_orch_model,
        name=_name,
        description=_desc,
    )
    orch_env.add_tool(_tool.mcp)


@orch_env.scenario("diagnose")
async def orch_diagnose(query: str) -> Any:
    """Diagnose an ops issue using specialized subagents.
    
    Args:
        query: The issue to diagnose (e.g., "Users report 500 errors on login")
    """
    system_prompt = f"""You are an ops diagnostics orchestrator with specialized subagents:

- **investigate_sentry**: Search for errors and analyze issues in Sentry
- **investigate_supabase**: Query database, check auth logs, analyze schema
- **investigate_railway**: Check deployments, get logs, manage services
- **investigate_kubernetes**: Check pod status, get logs, analyze cluster health
- **search_hud_docs**: Search HUD SDK documentation for architecture, v5 scenarios, task formats, etc.
- **investigate_github**: Search code, issues, PRs, and GitHub Actions workflows

**Issue to diagnose:**
{query}

**IMPORTANT: All subagents are READ-ONLY. They investigate but do NOT make changes.**

**Instructions:**
1. Use the appropriate subagent tools to investigate
2. Each tool takes a "query" parameter - describe what to look for
3. Correlate findings across services
4. If the issue involves HUD concepts (tasks, scenarios, rewards, evaluate_tool), use search_hud_docs to understand the expected behavior
5. If you need to check source code or recent changes, use investigate_github
6. Provide a comprehensive diagnosis with recommended actions for humans to take

**HUD-Specific Context:**
- v4 Tasks use `setup_tool` and `evaluate_tool` for scoring
- v5 Scenarios use `@env.scenario()` with two yields (prompt, then reward via read_resource)
- If `evaluate_tool` is NULL but using v5 scenarios, check if `read_resource` is being called

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
    prompt = f"""*** INCIDENT RESPONSE (READ-ONLY INVESTIGATION) ***

**Severity:** {sev.upper()}
**Description:** {desc}

You have specialized READ-ONLY subagents:
- investigate_sentry: Error analysis
- investigate_supabase: Database issues
- investigate_railway: Deployment status
- investigate_kubernetes: Cluster health
- search_hud_docs: HUD SDK documentation (for understanding expected behavior)
- investigate_github: Code, issues, PRs, and GitHub Actions

**Priority actions:**
1. Quickly assess scope
2. Identify root cause (use search_hud_docs if the issue involves HUD concepts)
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
    for name, _, desc in _subagents:
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
    """Test that all subagents can connect and optionally run queries."""
    from hud.tools import AgentTool
    from hud.agents import create_agent
    import hud
    
    from environments import sentry_env, supabase_env, railway_env, kubectl_env, hud_docs_env, github_env
    
    subagents = [
        ("Sentry", sentry_env, "List recent errors or issues"),
        ("Supabase", supabase_env, "List database tables"),
        ("Railway", railway_env, "List projects and their status"),
        ("kubectl", kubectl_env, "List nodes in the cluster"),
        ("HUD Docs", hud_docs_env, "What is the difference between v4 tasks and v5 scenarios?"),
        ("GitHub", github_env, "Search for recent commits in hud-evals/hud-python"),
    ]
    
    console.print("[bold]Testing subagent connections...[/bold]\n")
    
    for name, env, _ in subagents:
        try:
            async with env:
                tools = env.as_tools()
                console.print(f"  [green]+[/green] {name}: {len(tools)} tools")
        except Exception as e:
            console.print(f"  [red]x[/red] {name}: {e}")
    
    console.print()
    
    if run_queries:
        console.print("[bold]Running test queries through each subagent...[/bold]\n")
        
        for name, env, query in subagents:
            console.print(Panel(f"[bold]{name}[/bold]: {query}", border_style="cyan"))
            
            try:
                # Create AgentTool for this environment's investigate scenario
                tool = AgentTool(
                    env("investigate"),
                    model=model,
                    name=f"test_{name.lower()}",
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
