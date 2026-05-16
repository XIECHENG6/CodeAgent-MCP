"""
CodeAgent-MCP — HuggingFace Spaces Demo (Gradio).

Multi-Agent code generation with Planner → Coder → Reviewer loop.
"""

import asyncio
import json
import os
import time

import gradio as gr

from src.core.config import load_settings, load_agents_config
from src.core.llm_client import LLMClient
from src.core.orchestrator import Orchestrator
from src.agents import PlannerAgent, CoderAgent, ReviewerAgent


EXAMPLE_TASKS = [
    "实现一个 LRU Cache，支持 get 和 put 操作，要求 O(1) 时间复杂度",
    "实现一个简单的 Stack 数据结构，支持 push, pop, peek, is_empty 方法",
    "编写一个配置管理器，支持从 YAML/JSON 加载，支持点号路径访问如 config.get('db.host')",
    "实现一个令牌桶限流器 TokenBucketRateLimiter，支持 acquire() 和装饰器用法",
]


async def run_agents(requirement: str, api_key: str, provider: str, progress=gr.Progress()):
    if not api_key.strip():
        return "请输入 API Key", "", ""

    os.environ["OPENAI_API_KEY"] = api_key.strip()

    settings = load_settings()
    agents_config = load_agents_config()

    llm = LLMClient.from_settings(provider, settings)
    planner = PlannerAgent(agents_config["planner"], llm)
    coder = CoderAgent(agents_config["coder"], llm, mcp_manager=None)
    reviewer = ReviewerAgent(agents_config["reviewer"], llm)
    orchestrator = Orchestrator(
        planner=planner, coder=coder, reviewer=reviewer,
        config=settings["orchestrator"],
    )

    progress(0.1, desc="Planner 正在拆解任务...")
    start = time.time()
    result = await orchestrator.run(requirement)
    elapsed = time.time() - start

    code_blocks = []
    log_lines = []

    log_lines.append(f"**任务拆分**: {len(result.plan)} 个子任务")
    for i, task in enumerate(result.plan):
        log_lines.append(f"  T{i+1}: {task['description'][:80]}")
    log_lines.append("")

    for i, r in enumerate(result.results):
        score = r["review"]["score"] if r.get("review") else "N/A"
        status_icon = "✅" if r["status"] == "completed" else "⚠️"
        log_lines.append(
            f"{status_icon} **Task {i+1}**: score={score}/10, "
            f"attempts={r['attempts']}, status={r['status']}"
        )
        if r.get("code"):
            code_blocks.append(r["code"])

    log_lines.append("")
    log_lines.append(f"**总 Token**: {result.total_tokens:,}")
    log_lines.append(f"**耗时**: {elapsed:.1f}s")

    completed = sum(1 for r in result.results if r["status"] == "completed")
    scores = [r["review"]["score"] for r in result.results if r.get("review")]
    avg_score = sum(scores) / len(scores) if scores else 0

    stats = json.dumps({
        "completion_rate": f"{completed}/{len(result.results)}",
        "avg_score": round(avg_score, 1),
        "total_tokens": result.total_tokens,
        "elapsed_seconds": round(elapsed, 1),
    }, indent=2, ensure_ascii=False)

    return "\n\n".join(code_blocks), "\n".join(log_lines), stats


def create_demo():
    with gr.Blocks(title="CodeAgent-MCP", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            "# 🤖 CodeAgent-MCP\n"
            "**Multi-Agent Code Generation System** — "
            "Planner (任务拆解) → Coder (代码生成) → Reviewer (代码审查) 反馈循环\n\n"
            "基于 MCP 协议的多 Agent 协作代码开发系统。"
        )

        with gr.Row():
            with gr.Column(scale=1):
                api_key = gr.Textbox(
                    label="API Key (DeepSeek / OpenAI)",
                    type="password",
                    placeholder="sk-...",
                )
                provider = gr.Dropdown(
                    choices=["default", "siliconflow", "openai"],
                    value="default",
                    label="LLM Provider",
                )
                requirement = gr.Textbox(
                    label="开发需求",
                    placeholder="请描述你想实现的功能...",
                    lines=3,
                )
                examples = gr.Examples(
                    examples=[[e] for e in EXAMPLE_TASKS],
                    inputs=[requirement],
                )
                run_btn = gr.Button("🚀 开始生成", variant="primary")

            with gr.Column(scale=2):
                code_output = gr.Markdown(label="生成的代码")
                with gr.Row():
                    log_output = gr.Markdown(label="执行日志")
                    stats_output = gr.Code(label="统计数据", language="json")

        run_btn.click(
            fn=run_agents,
            inputs=[requirement, api_key, provider],
            outputs=[code_output, log_output, stats_output],
        )

        gr.Markdown(
            "---\n"
            "**架构**: 自研 300 行编排器，不依赖 LangChain | "
            "**项目系列**: small-llms-tool-use → agenttune → smallrag → CodeAgent-MCP\n\n"
            "[GitHub](https://github.com/XIECHENG6/CodeAgent-MCP)"
        )

    return demo


if __name__ == "__main__":
    demo = create_demo()
    demo.launch()
