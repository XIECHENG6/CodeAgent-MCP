"""
CodeAgent-MCP Comparison Experiments.

Runs ablation studies across:
  1. Single Agent (no Planner/Reviewer) vs Multi-Agent
  2. With MCP tools vs Without MCP tools
  3. Different LLM providers (DeepSeek / SiliconFlow / OpenAI)

Usage (on Colab):
    python -m eval.run_comparison --experiment all
    python -m eval.run_comparison --experiment ablation --tasks B1 B4 B7
    python -m eval.run_comparison --experiment providers --tasks B1
"""

import argparse
import asyncio
import json
import os
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
from eval.run_eval import load_benchmark, run_single_task, print_summary


async def run_single_agent_task(task: dict, settings: dict, agents_config: dict, provider: str) -> dict:
    """Run a task with Coder only (no Planner decomposition, no Reviewer loop)."""
    llm = LLMClient.from_settings(provider, settings)
    coder = CoderAgent(agents_config["coder"], llm, mcp_manager=None)

    start = time.time()
    try:
        code_output = await coder.run(
            f"请完成以下编程任务，输出完整代码：\n{task['description']}"
        )
        elapsed = time.time() - start
        return {
            "task_id": task["task_id"],
            "task_name": task["name"],
            "difficulty": task["difficulty"],
            "status": "completed",
            "review_score": None,
            "attempts": 1,
            "total_tokens": coder.total_tokens_used,
            "elapsed_seconds": round(elapsed, 1),
            "code_length": len(code_output),
            "mode": "single_agent",
            "provider": provider,
        }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "task_id": task["task_id"],
            "task_name": task["name"],
            "status": "error",
            "error": str(e),
            "elapsed_seconds": round(elapsed, 1),
            "mode": "single_agent",
            "provider": provider,
        }


async def run_ablation(tasks: list[dict], settings: dict, agents_config: dict, mcp_config: dict):
    """Compare: single-agent vs multi-agent, mcp vs no-mcp."""
    configs = [
        ("single_agent_nomcp", False, True),
        ("multi_agent_nomcp", False, False),
        ("multi_agent_mcp", True, False),
    ]

    all_results = {}

    for config_name, use_mcp, single_agent in configs:
        print(f"\n{'='*60}")
        print(f"Config: {config_name}")
        print(f"{'='*60}")
        results = []
        for i, task in enumerate(tasks):
            print(f"  [{i+1}/{len(tasks)}] {task['task_id']}: {task['name']}")
            if single_agent:
                result = await run_single_agent_task(task, settings, agents_config, "default")
            else:
                result = await run_single_task(
                    task, settings, agents_config, mcp_config,
                    provider="default", use_mcp=use_mcp,
                )
            result["config"] = config_name
            results.append(result)
            score = result.get("review_score", "N/A")
            print(f"    -> {result['status']} (score={score}, tokens={result.get('total_tokens', '?')})")
        all_results[config_name] = results

    return all_results


async def run_provider_comparison(tasks: list[dict], settings: dict, agents_config: dict, mcp_config: dict):
    """Compare different LLM providers on the same tasks."""
    providers = []
    for name in ["default", "siliconflow", "openai"]:
        if name in settings.get("providers", {}):
            providers.append(name)

    all_results = {}
    for provider in providers:
        print(f"\n{'='*60}")
        print(f"Provider: {provider}")
        print(f"{'='*60}")
        results = []
        for i, task in enumerate(tasks):
            print(f"  [{i+1}/{len(tasks)}] {task['task_id']}: {task['name']}")
            result = await run_single_task(
                task, settings, agents_config, mcp_config,
                provider=provider, use_mcp=False,
            )
            result["config"] = f"provider_{provider}"
            results.append(result)
            print(f"    -> {result['status']} (score={result.get('review_score', 'N/A')})")
        all_results[f"provider_{provider}"] = results

    return all_results


def print_comparison_table(all_results: dict):
    print(f"\n{'='*80}")
    print("COMPARISON RESULTS")
    print(f"{'='*80}")

    headers = ["Config", "Completion", "Avg Score", "Avg Tokens", "Avg Time"]
    print(f"\n{headers[0]:<25} {headers[1]:<12} {headers[2]:<12} {headers[3]:<12} {headers[4]:<10}")
    print("-" * 75)

    for config_name, results in all_results.items():
        total = len(results)
        completed = sum(1 for r in results if r["status"] == "completed")
        scores = [r["review_score"] for r in results if r.get("review_score") is not None]
        tokens = [r["total_tokens"] for r in results if r.get("total_tokens")]
        times = [r["elapsed_seconds"] for r in results if r.get("elapsed_seconds")]

        avg_score = f"{sum(scores)/len(scores):.1f}" if scores else "N/A"
        avg_tokens = f"{sum(tokens)/len(tokens):.0f}" if tokens else "N/A"
        avg_time = f"{sum(times)/len(times):.1f}s" if times else "N/A"

        print(f"{config_name:<25} {completed}/{total:<10} {avg_score:<12} {avg_tokens:<12} {avg_time:<10}")


def save_comparison(all_results: dict, experiment: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"comparison_{experiment}_{timestamp}.json"
    path = os.path.join(output_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "experiment": experiment,
            "timestamp": timestamp,
            "configs": {
                name: {
                    "total": len(results),
                    "completed": sum(1 for r in results if r["status"] == "completed"),
                    "avg_score": (
                        sum(r.get("review_score", 0) for r in results if r.get("review_score") is not None)
                        / max(1, sum(1 for r in results if r.get("review_score") is not None))
                    ),
                    "total_tokens": sum(r.get("total_tokens", 0) for r in results),
                    "results": results,
                }
                for name, results in all_results.items()
            },
        }, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to: {path}")
    return path


async def main():
    parser = argparse.ArgumentParser(description="CodeAgent-MCP Comparison Experiments")
    parser.add_argument("--experiment", choices=["ablation", "providers", "all"], default="ablation")
    parser.add_argument("--tasks", nargs="*", help="Task IDs (e.g., B1 B4)")
    parser.add_argument("--output", default="eval/results")
    args = parser.parse_args()

    tasks = load_benchmark()
    if args.tasks:
        tasks = [t for t in tasks if t["task_id"] in args.tasks]

    settings = load_settings()
    agents_config = load_agents_config()
    mcp_config = load_mcp_config()

    all_results = {}

    if args.experiment in ("ablation", "all"):
        results = await run_ablation(tasks, settings, agents_config, mcp_config)
        all_results.update(results)

    if args.experiment in ("providers", "all"):
        results = await run_provider_comparison(tasks, settings, agents_config, mcp_config)
        all_results.update(results)

    print_comparison_table(all_results)
    save_comparison(all_results, args.experiment, args.output)


if __name__ == "__main__":
    asyncio.run(main())
