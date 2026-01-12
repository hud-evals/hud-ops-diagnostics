"""Supabase Subagent - Database and auth investigation.

This subagent specializes in:
- Querying database tables and schema
- Checking auth and storage logs
- Analyzing database performance
"""

import asyncio
import logging
import os
import platform
import sys
from typing import Any

from dotenv import load_dotenv
from hud import Environment

load_dotenv()

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# =============================================================================
# SUPABASE ENVIRONMENT
# =============================================================================

supabase_env = Environment(name="supabase-agent")

# Connect to Supabase MCP server
IS_WINDOWS = platform.system() == "Windows"
supabase_token = os.getenv("SUPABASE_ACCESS_TOKEN")
supabase_project = os.getenv("SUPABASE_PROJECT_REF")

if supabase_token:
    logger.info("Connecting to Supabase MCP server...")
    if IS_WINDOWS:
        supabase_args = ["/c", "npx", "-y", "@supabase/mcp-server-supabase@latest"]
        if supabase_project:
            supabase_args.extend(["--project-ref", supabase_project])
        supabase_config = {
            "command": "cmd",
            "args": supabase_args,
            "env": {"SUPABASE_ACCESS_TOKEN": supabase_token}
        }
    else:
        supabase_args = ["-y", "@supabase/mcp-server-supabase@latest"]
        if supabase_project:
            supabase_args.extend(["--project-ref", supabase_project])
        supabase_config = {
            "command": "npx",
            "args": supabase_args,
            "env": {"SUPABASE_ACCESS_TOKEN": supabase_token}
        }
    supabase_env.connect_mcp_config({"supabase": supabase_config})
else:
    logger.warning("SUPABASE_ACCESS_TOKEN not set - Supabase tools unavailable")


# =============================================================================
# SCENARIO
# =============================================================================

@supabase_env.scenario("investigate")
async def investigate_database(
    query: str,
    expected_finding: str | None = None,  # Eval-only
) -> Any:
    """Investigate database or auth issues in Supabase.
    
    Args:
        query: What to investigate (table name, SQL query, or issue description)
        expected_finding: (Eval only) Expected finding for scoring
    """
    prompt = f"""You are a Supabase database specialist. Investigate the following:

**Query:** {query}

**IMPORTANT: This is a READ-ONLY investigation. Do NOT run any DDL or mutations.**

Use the available Supabase tools to:
1. List tables and check schema if relevant
2. Execute READ-ONLY SQL queries (SELECT only) to find data issues
3. Check logs (auth, postgres, edge-function) if relevant
4. Review security advisors for vulnerabilities

**HUD Schema Quick Reference:**
- `task_runs` - Individual task execution records (status, reward, created_at, etc.)
- `task_runs->telemetry column` - Full telemetry/trace data for each task run (tool calls, events)
- `runs` - Alias for `jobs` table
- `users`, `api_keys`, `transactions` - User and billing data

Provide a summary with:
- What you found in the database/logs
- Any issues or anomalies
- Root cause analysis
- Recommended actions (for human to take)"""

    response = yield prompt
    
    if expected_finding and response:
        yield 1.0 if expected_finding.lower() in response.lower() else 0.5
    else:
        yield 1.0 if response else 0.0


# =============================================================================
# TEST
# =============================================================================

async def test_supabase_tools():
    """Test that Supabase tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing Supabase Subagent")
    print("=" * 60 + "\n")
    
    async with supabase_env:
        tools = supabase_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools[:10]:
            print(f"  • {t.name}")
        if len(tools) > 10:
            print(f"  ... and {len(tools) - 10} more")
        
        # Try a simple tool call
        if any(t.name == "list_tables" for t in tools):
            try:
                result = await supabase_env.call_tool("list_tables")
                print(f"\n✓ list_tables: {str(result)[:200]}")
            except Exception as e:
                print(f"\n✗ list_tables failed: {e}")
        
        if any(t.name == "get_project_url" for t in tools):
            try:
                result = await supabase_env.call_tool("get_project_url")
                print(f"✓ get_project_url: {str(result)[:200]}")
            except Exception as e:
                print(f"✗ get_project_url failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_supabase_tools())

