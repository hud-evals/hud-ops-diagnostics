"""Internal Documentation Subagent - Search docs for architecture and concepts.

This subagent specializes in:
- Understanding system architecture and design patterns
- Finding documentation and code examples
- Explaining concepts and workflows
- Answering "how does X work?" questions
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
# DOCS ENVIRONMENT
# =============================================================================

docs_env = Environment(name="docs-agent")

# Connect to Docs MCP server (HTTP transport) if DOCS_MCP env var is set
docs_mcp_url = os.getenv("DOCS_MCP")

if docs_mcp_url:
    logger.info("Connecting to Docs MCP server at %s", docs_mcp_url)
    docs_env.connect_mcp_config({
        "docs": {
            "url": docs_mcp_url
        }
    })
else:
    logger.warning("DOCS_MCP not set - Docs tools unavailable")


# =============================================================================
# SCENARIO
# =============================================================================

@docs_env.scenario("investigate")
async def investigate_docs(
    query: str,
    must_include: list[str] | None = None,
) -> Any:
    """Search internal documentation for architecture and concepts.
    
    Args:
        query: What to look up (e.g., "authentication flow", "API reference", "deployment guide")
        must_include: (Eval only) Facts that must appear in response for full credit
    """
    prompt = f"""You are an internal documentation specialist. Answer the following:

**Query:** {query}

Use the available documentation search tools to:
1. Search for relevant documentation pages
2. Find code examples and API references
3. Explain concepts clearly

Provide a detailed answer including:
- Direct answers to the question
- Relevant code examples if applicable
- Links to documentation pages
- Any important caveats or notes

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

async def test_docs_tools():
    """Test that Docs tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing Docs Subagent")
    print("=" * 60 + "\n")
    
    async with docs_env:
        tools = docs_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools:
            print(f"  • {t.name}: {t.description[:60]}..." if t.description else f"  • {t.name}")
        
        # Try a search with the first available tool
        if tools:
            try:
                first_tool = tools[0]
                print(f"\nTrying {first_tool.name}...")
                result = await docs_env.call_tool(first_tool.name, query="getting started")
                print(f"✓ {first_tool.name} result: {str(result)[:500]}...")
            except Exception as e:
                print(f"✗ Tool call failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_docs_tools())

