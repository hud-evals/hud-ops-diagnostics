"""GitHub Subagent - Repository and code investigation.

This subagent specializes in:
- Searching code across repositories
- Investigating issues and pull requests
- Checking GitHub Actions workflows
- Repository analysis and code review
"""

import asyncio
import logging
import os
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
# GITHUB ENVIRONMENT
# =============================================================================

github_env = Environment(name="github-agent")

# Connect to GitHub MCP server (HTTP transport via Copilot)
github_pat = os.getenv("GITHUB_PAT")
_github_tools_available = False

if github_pat:
    logger.info("Connecting to GitHub MCP server...")
    github_env.connect_mcp_config({
        "github": {
            "url": "https://api.githubcopilot.com/mcp/",
            "headers": {
                "Authorization": f"Bearer {github_pat}"
            }
        }
    })
    _github_tools_available = True
else:
    logger.warning("GITHUB_PAT not set - GitHub tools unavailable")
    logger.warning("Get a PAT at: https://github.com/settings/tokens")


# =============================================================================
# SCENARIO
# =============================================================================

@github_env.scenario("investigate")
async def investigate_github(
    query: str,
    expected_finding: str | None = None,  # Eval-only
) -> Any:
    """Investigate code, issues, or workflows on GitHub.
    
    Args:
        query: What to investigate (repo, issue, code search, workflow)
        expected_finding: (Eval only) Expected finding for scoring
    """
    # Check if GitHub tools are available
    if not _github_tools_available:
        yield (
            "ERROR: GitHub tools are not available. GITHUB_PAT environment variable is not set.\n\n"
            "To enable GitHub investigation:\n"
            "1. Create a Personal Access Token at: https://github.com/settings/tokens\n"
            "2. Set the GITHUB_PAT environment variable\n\n"
            f"Original query (not investigated): {query}"
        )
        yield 0.0
        return

    prompt = f"""You are a GitHub specialist. Investigate the following:

**Query:** {query}

**IMPORTANT: This is a READ-ONLY investigation. Do NOT create issues, PRs, or modify anything.**

Use the available GitHub tools to:
1. Search code across repositories
2. Get repository information and files
3. Check issues and pull requests
4. Review GitHub Actions workflow runs

**HUD-Specific Repositories (all under hud-evals):**
- `hud-evals/hud-python` - Python SDK (Environment, scenarios, agents)
- `hud-evals/orchestrator` - Backend orchestrator (task execution, rewards)
- `hud-evals/platform-hud-so` - Platform frontend and API
- `hud-evals/telemetry` - Telemetry and tracing infrastructure

Provide a summary with:
- What you found (code, issues, workflows)
- Any relevant context
- Links to specific files/lines if applicable
- Recommended actions (for human to take)"""

    response = yield prompt
    
    if expected_finding and response:
        yield 1.0 if expected_finding.lower() in response.lower() else 0.5
    else:
        yield 1.0 if response else 0.0


# =============================================================================
# TEST
# =============================================================================

async def test_github_tools():
    """Test that GitHub tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing GitHub Subagent")
    print("=" * 60 + "\n")
    
    async with github_env:
        tools = github_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools[:15]:
            print(f"  • {t.name}")
        if len(tools) > 15:
            print(f"  ... and {len(tools) - 15} more")


if __name__ == "__main__":
    asyncio.run(test_github_tools())

