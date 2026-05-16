"""
CodeAgent-MCP Evaluation Runner.

Runs benchmark tasks through the orchestrator and collects metrics:
- Task completion rate
- Review scores
- Token usage
- Coder-Reviewer loop iterations
- Code quality checks (type hints, tests, etc.)

Usage:
    python -m eval.run_eval                        # run all tasks
    python -m eval.run_eval --tasks B1 B3          # run specific tasks
    python -m eval.run_eval --no-mcp               # without MCP tools
    python -m eval.run_eval --provider siliconflow  # different LLM
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings, load_agents_config, load_mcp_config
from src.core.llm_client import LLMClient
from src.core.orchestrator import Orchestrator
from src.agents import PlannerAgent, CoderAgent, ReviewerAgent
from src.mcp.client import MCPManager


def load_benchmark(path: str = None) -> list[dict]:
    if path is None:
        path = str(Path(__file__).parent / "benchmark_tasks.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["tasks"]


def analyze_code_output(code: str, criteria: dict) -> dict:
    checks = {}

    if criteria.get("has_class"):
        checks["has_class"] = bool(re.search(r'class\s+\w+', code))

    if criteria.get("has_type_hints"):
        checks["has_type_hints"] = bool(
            re.search(r'def\s+\w+\(.*:\s*\w+', code) or
            re.search(r'->\s*\w+', code)
        )

    if criteria.get("has_tests"):
        checks["has_tests"] = bool(
            re.search(r'def\s+test_\w+', code) or
            re.search(r'assert\s+', code) or
            re.search(r'unittest\.TestCase', code)
        )

    checks["has_docstring"] = bool(re.search(r'""".*?"""', code, re.DOTALL))
    checks["line_count"] = len(code.strip().split("\n"))

    return checks


async def run_single_task(
    task: dict,
    settings: dict,
    agents_config: dict,
    mcp_config: dict,
    provider: str,
    use_mcp: bool,
) -> dict:
    llm = LLMClient.from_settings(provider, settings)

    mcp_manager = None
    if use_mcp:
        try:
            mcp_manager = MCPManager()
            await mcp_manager.connect_from_config(mcp_config)
        except Exception as e:
            print(f"  [WARN] MCP connection failed: {e}")
            mcp_manager = None

    planner = PlannerAgent(agents_config["planner"], llm)
    coder = CoderAgent(agents_config["coder"], llm, mcp_manager)
    reviewer = ReviewerAgent(agents_config["reviewer"], llm)

    orchestrator = Orchestrator(
        planner=planner, coder=coder, reviewer=reviewer,
        config=settings["orchestrator"],
    )

    start_time = time.time()
    try:
        result = await orchestrator.run(task["description"])
        elapsed = time.time() - start_time

        final_code = ""
        final_score = 0
        total_attempts = 0
        status = "failed"

        for r in result.results:
            if r.get("code"):
                final_code += r["code"] + "\n"
            if r.get("review"):
                final_score = max(final_score, r["review"].get("score", 0))
            total_attempts += r.get("attempts", 0)
            if r["status"] == "completed":
                status = "completed"

        code_checks = analyze_code_output(final_code, task.get("criteria", {}))

        return {
            "task_id": task["task_id"],
            "task_name": task["name"],
            "difficulty": task["difficulty"],
            "status": status,
            "review_score": final_score,
            "attempts": total_attempts,
            "total_tokens": result.total_tokens,
            "elapsed_seconds": round(elapsed, 1),
            "code_checks": code_checks,
            "code_length": len(final_code),
            "subtasks_planned": len(result.plan),
            "use_mcp": use_mcp,
            "provider": provider,
        }

    except Exception as e:
        elapsed = time.time() - start_time
        return {
            "task_id": task["task_id"],
            "task_name": task["name"],
            "difficulty": task["difficulty"],
            "status": "error",
            "error": f"{type(e).__name__}: {str(e)}",
            "elapsed_seconds": round(elapsed, 1),
            "use_mcp": use_mcp,
            "provider": provider,
        }
    finally:
        if mcp_manager:
            await mcp_manager.disconnect_all()


def print_summary(results: list[dict]):
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)

    completed = sum(1 for r in results if r["status"] == "completed")
    total = len(results)
    print(f"\nCompletion rate: {completed}/{total} ({100*completed/total:.0f}%)")

    scores = [r["review_score"] for r in results if "review_score" in r]
    if scores:
        print(f"Average review score: {sum(scores)/len(scores):.1f}/10")

    tokens = [r["total_tokens"] for r in results if "total_tokens" in r]
    if tokens:
        print(f"Average tokens: {sum(tokens)/len(tokens):.0f}")

    times = [r["elapsed_seconds"] for r in results if "elapsed_seconds" in r]
    if times:
        print(f"Average time: {sum(times)/len(times):.1f}s")

    print(f"\n{'Task':<20} {'Status':<12} {'Score':<8} {'Attempts':<10} {'Tokens':<10} {'Time':<8}")
    print("-" * 70)
    for r in results:
        status = r["status"]
        score = r.get("review_score", "-")
        attempts = r.get("attempts", "-")
        tokens = r.get("total_tokens", "-")
        time_s = r.get("elapsed_seconds", "-")
        print(f"{r['task_name']:<20} {status:<12} {str(score):<8} {str(attempts):<10} {str(tokens):<10} {str(time_s):<8}")


def save_results(results: list[dict], output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    provider = results[0].get("provider", "unknown") if results else "unknown"
    mcp_tag = "mcp" if results[0].get("use_mcp") else "nomcp" if results else "unknown"
    filename = f"eval_{provider}_{mcp_tag}_{timestamp}.json"

    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": timestamp,
            "config": {
                "provider": provider,
                "use_mcp": results[0].get("use_mcp") if results else None,
            },
            "summary": {
                "total": len(results),
                "completed": sum(1 for r in results if r["status"] == "completed"),
                "avg_score": sum(r.get("review_score", 0) for r in results) / len(results) if results else 0,
                "total_tokens": sum(r.get("total_tokens", 0) for r in results),
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {path}")
    return path


async def main():
    parser = argparse.ArgumentParser(description="CodeAgent-MCP Evaluation")
    parser.add_argument("--tasks", nargs="*", help="Task IDs to run (e.g., B1 B3)")
    parser.add_argument("--provider", default="default", help="LLM provider")
    parser.add_argument("--no-mcp", action="store_true", help="Disable MCP tools")
    parser.add_argument("--output", default="eval/results", help="Output directory")
    parser.add_argument("--benchmark", default=None, help="Benchmark JSON path")
    args = parser.parse_args()

    tasks = load_benchmark(args.benchmark)

    if args.tasks:
        tasks = [t for t in tasks if t["task_id"] in args.tasks]
        if not tasks:
            print(f"No matching tasks found for: {args.tasks}")
            return

    settings = load_settings()
    agents_config = load_agents_config()
    mcp_config = load_mcp_config()

    use_mcp = not args.no_mcp
    print(f"Running {len(tasks)} benchmark tasks")
    print(f"Provider: {args.provider} | MCP: {use_mcp}")
    print("-" * 40)

    results = []
    for i, task in enumerate(tasks):
        print(f"\n[{i+1}/{len(tasks)}] {task['task_id']}: {task['name']} ({task['difficulty']})")
        result = await run_single_task(
            task, settings, agents_config, mcp_config,
            args.provider, use_mcp,
        )
        results.append(result)
        print(f"  -> {result['status']} (score: {result.get('review_score', 'N/A')})")

    print_summary(results)
    save_results(results, args.output)


if __name__ == "__main__":
    asyncio.run(main())
