---
title: CodeAgent-MCP
emoji: "\U0001F916"
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: "5.6.0"
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
---

# CodeAgent-MCP

Multi-Agent Code Generation System with MCP Protocol.

**Planner** (task decomposition) -> **Coder** (code generation) -> **Reviewer** (code review) feedback loop.

## How to use

1. Enter your DeepSeek / OpenAI API key
2. Choose a provider (default = DeepSeek)
3. Describe the code you want to generate
4. Click "Start" and watch the multi-agent system work

## Architecture

- **Planner Agent**: Decomposes complex requirements into 2-4 subtasks
- **Coder Agent**: Generates code with optional MCP tool integration
- **Reviewer Agent**: Scores code quality (1-10) and provides improvement suggestions
- **Orchestrator**: Manages Coder-Reviewer feedback loop until quality threshold is met

## Project Series

1. [small-llms-tool-use](https://github.com/XIECHENG6/small-llms-tool-use) - Function calling fine-tuning (86-89% exact match)
2. [agenttune](https://github.com/XIECHENG6/agenttune) - Multi-step ReAct reasoning (100% task success rate)
3. [smallrag](https://github.com/XIECHENG6/smallrag) - RAG optimization (chunk_size=512 + MMR + top-k=5)
4. **CodeAgent-MCP** (this project) - Multi-Agent system integration

[GitHub](https://github.com/XIECHENG6/CodeAgent-MCP)
