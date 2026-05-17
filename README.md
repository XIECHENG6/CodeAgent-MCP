<div align="center">

# CodeAgent-MCP

**Multi-Agent Code Generation System with MCP Protocol**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![HuggingFace Space](https://img.shields.io/badge/%F0%9F%A4%97%20Demo-HuggingFace%20Spaces-yellow)](https://huggingface.co/spaces/Cheng-1/CodeAgent-MCP)
[![HumanEval](https://img.shields.io/badge/HumanEval-90.2%25%20pass%401-brightgreen)](#humaneval-benchmark)

Three specialized agents collaborate through a feedback loop: **Planner** decomposes tasks, **Coder** generates code with tool access, **Reviewer** scores quality and requests fixes until the code meets standards.

[Live Demo](https://huggingface.co/spaces/Cheng-1/CodeAgent-MCP) | [Evaluation Results](#evaluation-results) | [Project Series](#project-series)

</div>

---

## Architecture

```
                        ┌───────────────────────────────────────┐
                        │            Orchestrator               │
                        │                                       │
  User Requirement ───► │  Planner ──► Coder ◄──── Reviewer     │
                        │              │    ▲        │          │
                        │              │    │ fix    │          │
                        │              │    └────────┘          │
                        │              │   score < 7 → retry    │
                        │              │   score ≥ 7 → done     │
                        └──────────────┼────────────────────────┘
                                       │ MCP Protocol (stdio)
                        ┌──────────────┼────────────────────────┐
                        │              ▼                        │
                        │  File Server  Shell Server  Git Server│
                        │  RAG Server (optional)                │
                        └───────────────────────────────────────┘
```

## Highlights

| | Feature | Detail |
|---|---------|--------|
| **Multi-Agent** | Planner + Coder + Reviewer feedback loop | Custom ~300-line orchestrator, no LangChain dependency |
| **MCP Tools** | 4 tool servers via standard MCP protocol | File ops, sandboxed shell, Git, RAG retrieval |
| **HumanEval** | **90.2% pass@1** (148/164) | Verified on the standard OpenAI benchmark |
| **Benchmark** | **100% completion**, avg score 8.9/10 | 8 tasks (easy/medium/hard), automated evaluation |
| **Optimization** | Prompt engineering for cost reduction | Planner: -85% tokens, Coder tools: -32% tokens |
| **Security** | Shell whitelist + path sandboxing | Only safe commands allowed, directory traversal blocked |
| **Live Demo** | Gradio app on HuggingFace Spaces | Enter a requirement, watch agents collaborate in real-time |

## Quick Start

```bash
# Install
pip install openai mcp pydantic pyyaml rich

# Configure
export OPENAI_API_KEY="your-deepseek-api-key"

# Run (multi-agent, no MCP tools)
python -m src.main --no-mcp "Implement an LRU Cache with O(1) get/put"

# Run (multi-agent + MCP tools)
python -m src.main "Implement an LRU Cache with O(1) get/put"

# Run evaluation
python -m eval.run_eval --tasks B1
```

## Evaluation Results

### HumanEval Benchmark

| Metric | Value |
|--------|-------|
| **pass@1** | **148/164 (90.2%)** |
| Model | DeepSeek-chat |
| Mode | Single agent (Coder only) |

### Custom Benchmark (8 tasks)

<table>
<tr><td>

| Configuration | Completion | Avg Score | Tokens |
|--------------|-----------|-----------|--------|
| single_agent | 3/3 | N/A | 2.5K |
| multi_agent (no-mcp) | **8/8** | **8.89** | 136K |
| multi_agent (mcp) | **8/8** | **8.95** | 3,035K |

</td><td>

| Difficulty | Tasks | Avg Score |
|-----------|-------|-----------|
| Easy | 2 | 8.85 |
| Medium | 3 | 9.07 |
| Hard | 3 | 8.73 |

</td></tr>
</table>

### Optimization Results

| Optimization | Before | After | Improvement |
|-------------|--------|-------|-------------|
| Planner prompt tuning | 6 subtasks, 400K tokens | 2 subtasks, 57K tokens | **-85% tokens**, +0.4 score |
| Coder tool-call rules | 1,165K tokens | 787K tokens | **-32% tokens**, quality maintained |
| B7/B8 workspace fix | Empty workspace, 606K tokens | 16KB+35KB output, 579K tokens | Files restored, -5~14% tokens |

### Key Findings

- **Single agent cuts corners**: Without Reviewer, B7 produced only 227 tokens of output
- **MCP mode produces real engineering artifacts**: source files + unit tests + integration demos
- **Prompt engineering has the highest ROI**: One sentence change cut Planner tokens by 85%
- **Orchestrator state management is critical**: Retry paths must re-inject workspace context

## Project Structure

```
CodeAgent-MCP/
├── src/
│   ├── core/           # LLM client, agent base (ReAct loop), orchestrator, config
│   ├── agents/         # Planner, Coder, Reviewer
│   ├── mcp/            # MCP client manager + 4 tool servers
│   └── main.py         # CLI entry point
├── eval/               # Benchmark tasks, evaluation runner, HumanEval adapter
├── config/             # LLM providers, agent prompts, MCP server config
├── deploy/             # HuggingFace Spaces deployment scripts
├── app.py              # Gradio demo
├── notebooks/          # Colab experiment notebooks + reports
└── tests/              # Unit tests
```

## Design Decisions

| Decision | Why |
|----------|-----|
| Custom framework, no LangChain | ~300 lines, fully explainable in interviews |
| Only Coder gets MCP tools | Planner/Reviewer are pure LLM calls, reducing complexity |
| 4-layer JSON fallback parser | LLM output format is unpredictable, need robust parsing |
| Shell command whitelist | Only python/pytest/ruff allowed, blocks rm/sudo/etc. |
| Explicit env var merging for MCP | Subprocess chains don't reliably inherit parent env |

## Project Series

This project is the capstone of a four-project progression from single-skill research to system integration:

| # | Project | Focus | Key Result |
|---|---------|-------|------------|
| 1 | [small-llms-tool-use](https://github.com/XIECHENG6/small-llms-tool-use) | Function calling fine-tuning | 86-89% exact match (QLoRA) |
| 2 | [agenttune](https://github.com/XIECHENG6/agenttune) | Multi-step ReAct reasoning | 100% task success rate |
| 3 | [smallrag](https://github.com/XIECHENG6/smallrag) | RAG optimization | chunk_size=512 + MMR + top-k=5 |
| 4 | **CodeAgent-MCP** (this repo) | Multi-Agent + MCP integration | 90.2% HumanEval, 8.9/10 benchmark |

## License

MIT
