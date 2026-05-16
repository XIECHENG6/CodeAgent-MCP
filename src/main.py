"""
CodeAgent-MCP main entry point.
Usage:
    python -m src.main "实现一个LRU Cache"
    python -m src.main --provider siliconflow "编写HTTP客户端"
"""

import argparse
import asyncio
import json

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from .core.config import load_settings, load_agents_config, load_mcp_config
from .core.llm_client import LLMClient
from .core.orchestrator import Orchestrator
from .agents import PlannerAgent, CoderAgent, ReviewerAgent
from .mcp.client import MCPManager
from .utils.logger import setup_logging

console = Console()


async def run(requirement: str, provider: str = "default", use_mcp: bool = True):
    setup_logging("INFO")

    settings = load_settings()
    agents_config = load_agents_config()
    mcp_config = load_mcp_config()

    console.print(Panel(requirement, title="[bold]User Requirement", border_style="blue"))

    llm = LLMClient.from_settings(provider, settings)

    mcp_manager = None
    if use_mcp:
        try:
            mcp_manager = MCPManager()
            await mcp_manager.connect_from_config(mcp_config)
            tool_names = list(mcp_manager.tools_registry.keys())
            console.print(f"[green]MCP tools available: {tool_names}")
        except Exception as e:
            console.print(f"[yellow]MCP connection failed ({e}), running without tools")
            mcp_manager = None

    planner = PlannerAgent(agents_config["planner"], llm)
    coder = CoderAgent(agents_config["coder"], llm, mcp_manager)
    reviewer = ReviewerAgent(agents_config["reviewer"], llm)

    orchestrator = Orchestrator(
        planner=planner,
        coder=coder,
        reviewer=reviewer,
        config=settings["orchestrator"],
    )

    console.print("\n[bold cyan]Starting multi-agent orchestration...\n")
    result = await orchestrator.run(requirement)

    console.print("\n" + "=" * 60)
    console.print(Panel(f"[bold green]Completed!"))
    console.print(f"Tasks: {len(result.plan)}")
    console.print(f"Total tokens: {result.total_tokens}")

    for i, task_result in enumerate(result.results):
        status = "✓" if task_result["status"] == "completed" else "⚠"
        score = task_result["review"]["score"] if task_result.get("review") else "N/A"
        console.print(
            f"  {status} Task {i+1}: score={score}, "
            f"attempts={task_result['attempts']}, status={task_result['status']}"
        )

    console.print("\n[bold]Final Code Output:[/bold]")
    for task_result in result.results:
        if task_result.get("code"):
            console.print(Markdown(task_result["code"]))

    if mcp_manager:
        await mcp_manager.disconnect_all()

    return result


def main():
    parser = argparse.ArgumentParser(description="CodeAgent-MCP")
    parser.add_argument("requirement", help="Development requirement")
    parser.add_argument("--provider", default="default", help="LLM provider (default/siliconflow/openai)")
    parser.add_argument("--no-mcp", action="store_true", help="Disable MCP tools")
    args = parser.parse_args()

    asyncio.run(run(args.requirement, args.provider, use_mcp=not args.no_mcp))


if __name__ == "__main__":
    main()
