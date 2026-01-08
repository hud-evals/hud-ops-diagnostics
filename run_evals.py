#!/usr/bin/env python3
"""Run Sentry investigation evals using HUD's native variant system.

Usage:
    python run_evals.py                    # Run all tasks with 4 models
    python run_evals.py --task 0           # Run just first task
    python run_evals.py --group 3          # Run 3x per variant for variance
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv

load_dotenv()

# Suppress noisy loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp.client.stdio").setLevel(logging.CRITICAL)  # Suppress MCP parse errors

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(levelname)s] %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "claude-sonnet-4-5",
    "o3-mini",
]


async def run_with_variants(task_data: dict, models: list[str], group: int = 1):
    """Run a single task across all model variants using hud.eval."""
    import hud
    from hud.agents import create_agent
    from environments.sentry import sentry_env
    
    task_name = task_data.get("name", "unnamed")
    args = task_data.get("args", {})
    
    # Create task
    task = sentry_env("investigate", **args)
    
    print(f"\n{'='*60}")
    print(f"Task: {task_name}")
    print(f"Models: {models}")
    print(f"Group size: {group}")
    print(f"{'='*60}\n")
    
    # Run with variants!
    async with hud.eval(
        task,
        variants={"model": models},
        group=group,
    ) as ctx:
        model = ctx.variants["model"]
        print(f"Running with {model}...")
        
        agent = create_agent(model)
        result = await agent.run(ctx, max_steps=15)
        
        # The scenario handles scoring via must_include/must_not_include
        print(f"  → Reward: {ctx.reward}")
    
    # Print results
    print(f"\n{'='*60}")
    print("Results:")
    print(f"{'='*60}")
    
    for r in ctx.results:
        model = r.variants.get("model", "unknown")
        reward = r.reward if r.reward is not None else 0.0
        status = "✓" if reward >= 0.75 else "✗"
        print(f"  {status} {model}: {reward:.2f}")
    
    return ctx.results


async def run_all_tasks(tasks: list[dict], models: list[str], group: int = 1):
    """Run all tasks with variants."""
    from rich.console import Console
    from rich.table import Table
    
    console = Console()
    all_results = []
    
    for task_data in tasks:
        results = await run_with_variants(task_data, models, group)
        all_results.append({
            "task": task_data.get("name"),
            "results": [
                {"model": r.variants.get("model"), "reward": r.reward or 0.0}
                for r in results
            ]
        })
    
    # Summary table
    table = Table(title="\nFinal Results")
    table.add_column("Task", style="cyan")
    for model in models:
        table.add_column(model.split("/")[-1], justify="center")
    
    for task_result in all_results:
        row = [task_result["task"]]
        for model in models:
            result = next(
                (r for r in task_result["results"] if r["model"] == model),
                None
            )
            if result:
                reward = result["reward"]
                if reward >= 0.75:
                    cell = f"[green]{reward:.2f}[/green]"
                elif reward >= 0.5:
                    cell = f"[yellow]{reward:.2f}[/yellow]"
                else:
                    cell = f"[red]{reward:.2f}[/red]"
            else:
                cell = "-"
            row.append(cell)
        table.add_row(*row)
    
    console.print(table)


async def main():
    parser = argparse.ArgumentParser(description="Run Sentry evals with HUD variants")
    parser.add_argument("--tasks-file", default="tasks.json", help="Tasks file")
    parser.add_argument("--task", type=int, help="Run specific task index")
    parser.add_argument("--models", nargs="+", default=MODELS, help="Models to test")
    parser.add_argument("--group", type=int, default=1, help="Runs per variant")
    
    args = parser.parse_args()
    
    # Load tasks
    with open(args.tasks_file) as f:
        all_tasks = json.load(f)
    
    if args.task is not None:
        tasks = [all_tasks[args.task]]
    else:
        tasks = all_tasks
    
    if len(tasks) == 1:
        await run_with_variants(tasks[0], args.models, args.group)
    else:
        await run_all_tasks(tasks, args.models, args.group)


if __name__ == "__main__":
    asyncio.run(main())
