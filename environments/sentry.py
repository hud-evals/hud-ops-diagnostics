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
    mcp_env = {"SENTRY_ACCESS_TOKEN": sentry_token}
    if os.getenv("OPENAI_API_KEY"):
        mcp_env["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

    if IS_WINDOWS:
        sentry_config = {
            "command": "cmd",
            "args": ["/c", "npx", "-y", "@sentry/mcp-server@latest"],
            "env": mcp_env
        }
    elif os.environ.get("IS_TAIGA") == "1":
        # Bypass npx (too slow for Taiga's startup timeout).
        # Runs the pre-installed binary directly via node.
        sentry_config = {
            "command": "node",
            "args": ["/usr/local/lib/node_modules/@sentry/mcp-server/dist/index.js"],
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
# TAIGA TOOLS (only exposed when running on Taiga platform)
# =============================================================================
#
# When IS_TAIGA=1, registers setup_problem and grade_problem tools.
# Taiga calls setup_problem to initialize the task (returns the prompt),
# then the agent investigates using Sentry MCP tools, and finally
# Taiga calls grade_problem with the full transcript for scoring.
# =============================================================================

if os.environ.get("IS_TAIGA") == "1":
    import yaml

    TASKS_FILE = os.environ.get("TASKS_FILE", "/app/tasks.yaml")

    def _load_tasks() -> list[dict]:
        """Load task definitions from tasks.yaml."""
        tasks_file = TASKS_FILE
        if not os.path.exists(tasks_file):
            alt = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tasks.yaml")
            if os.path.exists(alt):
                tasks_file = alt
            else:
                logger.warning("Tasks file not found: %s", tasks_file)
                return []
        with open(tasks_file, "r", encoding="utf-8") as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        return data.get("tasks", []) if isinstance(data, dict) else data

    @sentry_env.tool()
    async def setup_problem(
        problem_id: str,
        task_prompt: str | None = None,
        rubric: Any | None = None,
        system_prompt: str | None = None,
        selected_folder: str | None = None,
        grader_metadata: Any | None = None,
        metadata: Any | None = None,
        preloaded_files: Any | None = None,
        output_directory: str | None = None,
        domain_allowlist: Any | None = None,
        enable_anthropic_api: bool | None = None,
        extra_fields: Any | None = None,
    ) -> str:
        """Setup the problem for the given task id.

        Returns the task prompt for the agent to investigate.
        """
        logger.info("[TAIGA] setup_problem called with problem_id: %s", problem_id)
        tasks = _load_tasks()
        task = next((t for t in tasks if t["name"] == problem_id), None)
        if not task:
            return f"Task {problem_id} not found"
        return task_prompt if task_prompt else task["prompt"]

    @sentry_env.tool()
    async def grade_problem(
        problem_id: str,
        transcript: str,
        selected_folder: str | None = None,
        grader_metadata: Any | None = None,
        metadata: Any | None = None,
        task_prompt: str | None = None,
        rubric: Any | None = None,
        system_prompt: str | None = None,
        preloaded_files: Any | None = None,
        output_directory: str | None = None,
        domain_allowlist: Any | None = None,
        enable_anthropic_api: bool | None = None,
        extra_fields: Any | None = None,
    ) -> dict:
        """Grade the problem using must_include/must_not_include string matching."""
        logger.info("[TAIGA] grade_problem called for %s", problem_id)
        tasks = _load_tasks()
        task = next((t for t in tasks if t["name"] == problem_id), None)
        if not task:
            return {
                "subscores": {"error": 0.0},
                "weights": {"error": 1},
                "metadata": {"error": f"Task {problem_id} not found"},
            }

        response_lower = transcript.lower()
        must_include = task.get("must_include", [])
        must_not_include = task.get("must_not_include", [])

        subscores = {}
        weights = {}

        # Count total positive criteria for weight normalization
        num_positive = len(must_include) if must_include else 1
        positive_weight = round(1.0 / num_positive, 3)

        # Each must_include fact is a criterion
        if must_include:
            for i, fact in enumerate(must_include):
                key = f"includes_{i + 1}"
                found = fact.lower() in response_lower
                subscores[key] = 1.0 if found else 0.0
                weights[key] = positive_weight

        # must_not_include: if any forbidden fact is present, zero out everything
        if must_not_include:
            has_mistake = any(bad.lower() in response_lower for bad in must_not_include)
            if has_mistake:
                for key in subscores:
                    subscores[key] = 0.0

        # Fallback if no criteria defined
        if not subscores:
            subscores = {"result": 1.0}
            weights = {"result": 1.0}

        score = round(sum(subscores[k] * weights[k] for k in subscores), 3)
        logger.info("[TAIGA] grade_problem result: score=%s subscores=%s", score, subscores)

        return {
            "subscores": subscores,
            "weights": weights,
            "metadata": {
                "score": score,
                "must_include": must_include,
                "must_not_include": must_not_include,
            },
        }

    logger.info("[TAIGA] Registered setup_problem and grade_problem tools")


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
    if "--test" in sys.argv:
        asyncio.run(test_sentry_tools())
    else:
        sentry_env.run()

