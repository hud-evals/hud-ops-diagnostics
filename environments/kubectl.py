"""kubectl Subagent - Kubernetes cluster investigation.

This subagent specializes in:
- Checking pod status and health
- Getting container logs
- Investigating cluster events and issues
"""

import asyncio
import logging
import sys
from typing import Any

from dotenv import load_dotenv
from hud import Environment

load_dotenv()

# Import kubectl tools from local tools folder
from environments.tools.kubectl import router as kubectl_router

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s | %(name)s | %(message)s",
    force=True,
)
logger = logging.getLogger(__name__)

# =============================================================================
# KUBECTL ENVIRONMENT
# =============================================================================

kubectl_env = Environment(name="kubectl-agent")

# Include kubectl tools
kubectl_env.include_router(kubectl_router)


# =============================================================================
# SCENARIO
# =============================================================================

@kubectl_env.scenario("investigate")
async def investigate_cluster(
    query: str,
    namespace: str = "default",
    expected_finding: str | None = None,  # Eval-only
) -> Any:
    """Investigate Kubernetes cluster issues.
    
    Args:
        query: What to investigate (pod name, error description, etc.)
        namespace: Kubernetes namespace to focus on
        expected_finding: (Eval only) Expected finding for scoring
    """
    prompt = f"""You are a Kubernetes specialist. Investigate the following:

**Query:** {query}
**Namespace:** {namespace}

**IMPORTANT: This is a READ-ONLY investigation. Do NOT make any changes.**

Use the available kubectl tools to:
1. Get pods and their status
2. Check events for errors or warnings
3. Get logs from relevant pods
4. Describe pods with issues
5. Check node health if relevant

Provide a summary with:
- Current cluster state
- Any failing or unhealthy pods
- Error patterns in logs
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

async def test_kubectl_tools():
    """Test that kubectl tools are accessible."""
    print("\n" + "=" * 60)
    print("Testing kubectl Subagent")
    print("=" * 60 + "\n")
    
    async with kubectl_env:
        tools = kubectl_env.as_tools()
        print(f"Found {len(tools)} tools:")
        for t in tools[:10]:
            print(f"  • {t.name}")
        if len(tools) > 10:
            print(f"  ... and {len(tools) - 10} more")
        
        # Try a simple tool call
        if any(t.name == "kubectl_get_nodes" for t in tools):
            try:
                result = await kubectl_env.call_tool("kubectl_get_nodes")
                print(f"\n✓ kubectl_get_nodes: {str(result)[:200]}")
            except Exception as e:
                print(f"\n✗ kubectl_get_nodes failed: {e}")
        
        if any(t.name == "kubectl_get_pods" for t in tools):
            try:
                result = await kubectl_env.call_tool("kubectl_get_pods", namespace="default")
                print(f"✓ kubectl_get_pods: {str(result)[:200]}")
            except Exception as e:
                print(f"✗ kubectl_get_pods failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_kubectl_tools())

