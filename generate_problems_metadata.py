#!/usr/bin/env python3
"""Generate Taiga-compatible problems metadata JSON from tasks.yaml.

Usage:
    python generate_problems_metadata.py                           # tasks.yaml -> stdout
    python generate_problems_metadata.py --output problems.json    # tasks.yaml -> problems.json
    python generate_problems_metadata.py --image us-east1-docker.pkg.dev/gcp-taiga/hud/ops_diagnostics:0.1
    python generate_problems_metadata.py --task-ids find_responses_schema_error,aws_credential_failure
"""

import argparse
import json

import yaml

DEFAULT_IMAGE = "us-east1-docker.pkg.dev/gcp-taiga/hud/ops_diagnostics:0.02"
DEFAULT_SYSTEM_PROMPT = (
    "You are a Sentry specialist. Use the available Sentry tools to investigate the query.\n\n"
    "IMPORTANT: This is a READ-ONLY investigation. Do NOT modify issue status or assignments.\n\n"
    "Use the available Sentry tools to:\n"
    "1. Search for related issues or events\n"
    "2. Get issue details if you find relevant issues\n"
    "3. Analyze with Seer if available for root cause\n\n"
    "Provide a detailed summary including:\n"
    "- Issue ID(s) found\n"
    "- Root cause analysis with specific technical details\n"
    "- Affected users/occurrences\n"
    "- Recommended fixes (for human to implement)"
)


def convert_task_to_problem(task, image):
    """Convert a single task from tasks.yaml to Taiga problem format."""
    problem = {
        "image": image,
        "startup_command": "/app/start.sh",
        "id": task["name"],
        "required_tools": [],
        "metadata": {
            "difficulty": task.get("difficulty", "medium"),
        },
        "system_prompt": DEFAULT_SYSTEM_PROMPT,
        "task_prompt": task["prompt"],
        "enable_anthropic_api": True,
        "domain_allowlist": ["*"],
    }

    # Build rubric from must_include/must_not_include for Taiga's grader info.
    # Actual grading is done by our grade_problem tool via exact string matching.
    rubric = []
    for fact in task.get("must_include", []):
        rubric.append({"criterion": f"Response includes: {fact}", "weight": 1})
    for bad in task.get("must_not_include", []):
        rubric.append({"criterion": f"Response does NOT include: {bad}", "weight": -1})
    if rubric:
        problem["rubric"] = rubric

    return problem


def main():
    parser = argparse.ArgumentParser(description="Generate Taiga problems metadata")
    parser.add_argument(
        "--tasks-file",
        type=str,
        default="tasks.yaml",
        help="Path to the tasks file (default: tasks.yaml)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "--image",
        type=str,
        default=DEFAULT_IMAGE,
        help=f"Docker image path (default: {DEFAULT_IMAGE})",
    )
    parser.add_argument(
        "--name",
        type=str,
        default="TGA-ops-diagnostics-demo",
        help="Problem set name",
    )
    parser.add_argument(
        "--task-ids",
        type=str,
        default=None,
        help="Comma-separated list of task IDs to include (default: all)",
    )
    args = parser.parse_args()

    with open(args.tasks_file, "r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    tasks = data.get("tasks", []) if isinstance(data, dict) else data

    if args.task_ids:
        task_id_set = set(args.task_ids.split(","))
        tasks = [t for t in tasks if t["name"] in task_id_set]

    problems = [convert_task_to_problem(task, args.image) for task in tasks]

    output = {
        "problem_set": {
            "owner": "hud",
            "name": args.name,
            "description": "Ops diagnostics benchmark tasks",
            "problems": problems,
        }
    }

    output_json = json.dumps(output, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"Generated {len(problems)} problems -> {args.output}")
    else:
        print(output_json)


if __name__ == "__main__":
    main()
