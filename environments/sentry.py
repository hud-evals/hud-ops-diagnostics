"""Sentry Subagent - Error monitoring and issue investigation.

This subagent specializes in:
- Finding and analyzing Sentry issues
- Root cause analysis with Seer AI
- Searching error events and logs
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
# SENTRY ENVIRONMENT
# =============================================================================

sentry_env = Environment(name="sentry-agent")

# Connect to Sentry MCP server
IS_WINDOWS = platform.system() == "Windows"
sentry_token = os.getenv("SENTRY_AUTH_TOKEN")

if sentry_token:
    logger.info("Connecting to Sentry MCP server...")
    # Build env dict - include OPENAI_API_KEY for AI-powered search
    mcp_env = {"SENTRY_ACCESS_TOKEN": sentry_token}
    if os.getenv("OPENAI_API_KEY"):
        mcp_env["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    
    if IS_WINDOWS:
        sentry_config = {
            "command": "cmd",
            "args": ["/c", "npx", "-y", "@sentry/mcp-server@latest"],
            "env": mcp_env
        }
    else:
        sentry_config = {
            "command": "npx",
            "args": ["-y", "@sentry/mcp-server@latest"],
            "env": mcp_env
        }
    sentry_env.connect_mcp_config({"sentry": sentry_config})
else:
    logger.warning("SENTRY_AUTH_TOKEN not set - Sentry tools unavailable")


# =============================================================================
# SCENARIO
# =============================================================================

@sentry_env.scenario("investigate")
async def investigate_issue(
    query: str,
    # Eval-only params - hidden from orchestrator, used for scoring
    must_include: list[str] | None = None,
    must_not_include: list[str] | None = None,
) -> Any:
    """Investigate errors in Sentry.
    
    Args:
        query: What to investigate (issue ID, error message, or search query)
        must_include: (Eval only) Facts that must appear in response for full credit
        must_not_include: (Eval only) Common mistakes to penalize
    """
    prompt = f"""You are a Sentry specialist. Investigate the following:

**Query:** {query}

**IMPORTANT: This is a READ-ONLY investigation. Do NOT modify issue status or assignments.**

Use the available Sentry tools to:
1. Search for related issues or events
2. Get issue details if you find relevant issues
3. Analyze with Seer if available for root cause

Provide a detailed summary including:
- Issue ID(s) found
- Root cause analysis with specific technical details
- Affected users/occurrences
- Recommended fixes (for human to implement)"""

    response = yield prompt
    
    if not response:
        yield 0.0
        return
    
    response_lower = response.lower()
    score = 1.0
    
    # All required facts must be present for full credit
    if must_include:
        all_found = all(fact.lower() in response_lower for fact in must_include)
        score = 1.0 if all_found else 0.0
    
    # Any mistake = fail
    if must_not_include and score > 0:
        has_mistake = any(bad.lower() in response_lower for bad in must_not_include)
        if has_mistake:
            score = 0.0
    
    yield score


# =============================================================================
# TEST
# =============================================================================

async def test_sentry_tools():
    """Test that Sentry tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing Sentry Subagent")
    print("=" * 60 + "\n")
    
    async with sentry_env:
        tools = sentry_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools[:10]:  # Show first 10
            print(f"  • {t.name}")
        if len(tools) > 10:
            print(f"  ... and {len(tools) - 10} more")
        
        # Try a simple tool call
        if any(t.name == "whoami" for t in tools):
            try:
                result = await sentry_env.call_tool("whoami")
                print(f"\n✓ whoami: {str(result)[:200]}")
            except Exception as e:
                print(f"\n✗ whoami failed: {e}")
        
        if any(t.name == "find_organizations" for t in tools):
            try:
                result = await sentry_env.call_tool("find_organizations")
                print(f"✓ find_organizations: {str(result)[:200]}")
            except Exception as e:
                print(f"✗ find_organizations failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_sentry_tools())

