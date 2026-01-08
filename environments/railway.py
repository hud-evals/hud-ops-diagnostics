"""Railway Subagent - Deployment and infrastructure investigation.

This subagent specializes in:
- Checking deployment status and logs
- Managing services and environments
- Investigating deployment failures
"""

import asyncio
import logging
import os
import sys
from typing import Any

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
# RAILWAY ENVIRONMENT
# =============================================================================

railway_env = Environment(name="railway-agent")

# Use custom CLI wrapper tools (more reliable than MCP server which needs browser auth)
from environments.tools.railway import router as railway_router
railway_env.include_router(railway_router)

railway_token = os.getenv("RAILWAY_API_TOKEN")
if not railway_token:
    logger.warning("RAILWAY_API_TOKEN not set - Railway tools may not work")


# =============================================================================
# SCENARIO
# =============================================================================

@railway_env.scenario("investigate")
async def investigate_deployment(
    query: str,
    expected_finding: str | None = None,  # Eval-only
) -> Any:
    """Investigate deployment or infrastructure issues in Railway.
    
    Args:
        query: What to investigate (service name, deployment issue, etc.)
        expected_finding: (Eval only) Expected finding for scoring
    """
    prompt = f"""You are a Railway deployment specialist. Investigate the following:

**Query:** {query}

**IMPORTANT: This is a READ-ONLY investigation. Do NOT make any changes.**

Use the available Railway tools to:
1. List projects and services to find the relevant ones
2. Check recent deployments and their status
3. Get logs for failing deployments
4. Check environment variables if needed

Provide a summary with:
- Current deployment status
- Any recent failures or issues
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

async def test_railway_tools():
    """Test that Railway tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing Railway Subagent")
    print("=" * 60 + "\n")
    
    async with railway_env:
        tools = railway_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools[:10]:
            print(f"  - {t.name}")
        if len(tools) > 10:
            print(f"  ... and {len(tools) - 10} more")
        
        # Try listing projects
        if any(t.name == "railway_list_projects" for t in tools):
            try:
                result = await railway_env.call_tool("railway_list_projects")
                # Parse the MCP result to get actual content
                if hasattr(result, 'content'):
                    for block in result.content:
                        if hasattr(block, 'text'):
                            print(f"\n+ railway_list_projects:\n{block.text[:500]}")
                else:
                    print(f"\n+ railway_list_projects: {result}")
            except Exception as e:
                print(f"\nx railway_list_projects failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_railway_tools())

