"""HUD Documentation Subagent - Search HUD docs for architecture and concepts.

This subagent specializes in:
- Understanding HUD architecture (v4 vs v5 tasks, scenarios, etc.)
- Finding SDK documentation and code examples
- Explaining MCP protocol and environment patterns
- Answering "how does X work in HUD?" questions
"""

import asyncio
import logging
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
# HUD DOCS ENVIRONMENT
# =============================================================================

hud_docs_env = Environment(name="hud-docs-agent")

# Connect to HUD Docs MCP server (HTTP transport)
logger.info("Connecting to HUD Docs MCP server...")
hud_docs_env.connect_mcp_config({
    "hud-docs": {
        "url": "https://docs.hud.ai/mcp"
    }
})


# =============================================================================
# SCENARIO
# =============================================================================

@hud_docs_env.scenario("investigate")
async def investigate_hud_docs(
    query: str,
    must_include: list[str] | None = None,
) -> Any:
    """Search HUD documentation for architecture and concepts.
    
    Args:
        query: What to look up (e.g., "v5 scenarios", "evaluate_tool", "MCP protocol")
        must_include: (Eval only) Facts that must appear in response for full credit
    """
    prompt = f"""You are a HUD SDK documentation specialist. Answer the following:

**Query:** {query}

Use the available HUD documentation search tools to:
1. Search for relevant documentation pages
2. Find code examples and API references
3. Explain concepts clearly

Provide a detailed answer including:
- Direct answers to the question
- Relevant code examples if applicable
- Links to documentation pages
- Any important caveats or notes

**Key HUD Concepts to be aware of:**
- v4 Tasks: Use setup_tool and evaluate_tool 
- v5 Scenarios: Use @env.scenario() with two yields (prompt, then reward)
- Environment: Unified class for tools, setup, and scoring
- MCP: Model Context Protocol - how agents call tools
- Tasks: Define what agents should accomplish with scoring

Focus on being accurate and citing the documentation."""

    response = yield prompt
    
    if not response:
        yield 0.0
        return
    
    response_lower = response.lower()
    score = 0.0
    
    if must_include:
        matches = sum(1 for fact in must_include if fact.lower() in response_lower)
        score = matches / len(must_include)
    else:
        score = 1.0
    
    yield max(0.0, min(1.0, score))


# =============================================================================
# TEST
# =============================================================================

async def test_hud_docs_tools():
    """Test that HUD Docs tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing HUD Docs Subagent")
    print("=" * 60 + "\n")
    
    async with hud_docs_env:
        tools = hud_docs_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools:
            print(f"  • {t.name}: {t.description[:60]}..." if t.description else f"  • {t.name}")
        
        # Try a search
        if any(t.name == "SearchHud" for t in tools):
            try:
                result = await hud_docs_env.call_tool("SearchHud", query="v5 scenarios")
                print(f"\n✓ SearchHud result: {str(result)[:500]}...")
            except Exception as e:
                print(f"\n✗ SearchHud failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_hud_docs_tools())

