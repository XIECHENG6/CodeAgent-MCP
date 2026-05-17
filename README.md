# CodeAgent-MCP

基于 MCP 协议的多 Agent 协作代码开发系统。三个 Agent 各司其职：Planner 拆解任务、Coder 编写代码并调用工具、Reviewer 审查评分，通过编排器实现 Coder-Reviewer 反馈循环，直到代码质量达标。

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Orchestrator                       │
│                                                     │
│  User Requirement                                   │
│       │                                             │
│       ▼                                             │
│  ┌─────────┐    task list    ┌─────────┐            │
│  │ Planner │ ──────────────► │  Coder  │◄──┐        │
│  └─────────┘                 └────┬────┘   │        │
│                                   │        │ fix    │
│                              code │        │        │
│                                   ▼        │        │
│                            ┌──────────┐    │        │
│                            │ Reviewer │────┘        │
│                            └──────────┘             │
│                             score < 7? → retry      │
│                             score ≥ 7? → done       │
└─────────────────────────────────────────────────────┘
         │
         │ MCP Protocol (stdio)
         ▼
┌─────────────────────────────────────────────────────┐
│              MCP Tool Servers                        │
│                                                     │
│  ┌────────────┐ ┌─────────────┐ ┌────────────┐     │
│  │ File Server│ │ Shell Server│ │ Git Server │     │
│  │ read/write │ │ exec (沙箱) │ │ status/diff│     │
│  │ list/search│ │ 白名单命令  │ │ log/commit │     │
│  └────────────┘ └─────────────┘ └────────────┘     │
│                                                     │
│  ┌─────────────────────────────────┐                │
│  │ RAG Server (可选)               │                │
│  │ index / query (MMR) / status   │                │
│  │ BGE embedding + FAISS          │                │
│  └─────────────────────────────────┘                │
└─────────────────────────────────────────────────────┘
```

## Features

- **多 Agent 协作**: Planner 任务拆解 → Coder 代码生成 → Reviewer 评分循环
- **MCP 工具集成**: 通过标准 MCP 协议接入文件操作、Shell 执行、Git 操作、RAG 检索
- **自研框架**: ~300 行编排器，不依赖 LangChain/LlamaIndex，每一行可解释
- **安全沙箱**: Shell 命令白名单、文件路径安全校验、操作超时限制
- **多 LLM 支持**: DeepSeek / SiliconFlow / OpenAI 统一接口，可配置切换
- **JSON 容错解析**: 4 层 fallback（JSON block → code block → raw JSON → regex 提取）
- **评测框架**: 8 个 benchmark 任务，自动化评分与对比实验

## Quick Start

### 1. 安装依赖

```bash
pip install openai mcp pydantic pyyaml rich
```

### 2. 配置 API Key

```bash
export OPENAI_API_KEY="your-deepseek-api-key"
```

### 3. 运行

```bash
# 多 Agent + MCP 工具
python -m src.main "实现一个 LRU Cache"

# 仅 LLM（不使用 MCP 工具）
python -m src.main --no-mcp "实现一个 LRU Cache"

# 使用其他 LLM provider
python -m src.main --provider siliconflow "编写 HTTP 客户端"
```

### 4. 运行评测

```bash
# 单任务
python -m eval.run_eval --tasks B1

# 全部 benchmark
python -m eval.run_eval

# 对比实验 (单Agent vs 多Agent vs MCP)
python -m eval.run_comparison --experiment ablation --tasks B1 B4 B7
```

## Evaluation Results

### Full Benchmark (8 tasks: LRU Cache, BST, HTTP Retry, CSV Analyzer, Rate Limiter, Markdown Parser, Config Manager, Async Task Queue)

| Configuration | Completion | Avg Score | Total Tokens | Avg Time/Task |
|---------------|-----------|-----------|-------------|---------------|
| multi_agent_nomcp | **8/8 (100%)** | 8.89 | 136K | 70s |
| multi_agent_mcp | **8/8 (100%)** | 8.95 | 3,035K | 379s |

### Ablation Study (B1, B4, B7)

| Configuration | Completion | Avg Score | Avg Tokens | Avg Time |
|---------------|-----------|-----------|------------|----------|
| single_agent_nomcp | 3/3 | N/A | 2,524 | 16s |
| multi_agent_nomcp | 3/3 | 8.6 | 10,821 | 50s |
| multi_agent_mcp | 3/3 | 8.8 | 390,426 | 379s |

### Score by Difficulty (no-mcp, 8 tasks)

| Difficulty | Tasks | Avg Score | Avg Tokens |
|-----------|-------|-----------|------------|
| easy | 2 | 8.85 | 16,265 |
| medium | 3 | 9.07 | 11,702 |
| hard | 3 | 8.73 | 22,839 |

### MCP Workspace Verification (B7/B8 Fix)

修复 Coder-Reviewer 循环中 workspace 上下文丢失的 bug 后，MCP 模式能正确产出工程文件：

| Task | Workspace Output | Tokens | Score | Code Checks |
|------|-----------------|--------|-------|-------------|
| B7 config_manager | `config_manager.py` (16KB) | 579K | 8.5 | class ✓ types ✓ tests ✓ docs ✓ |
| B8 async_task_queue | 3 files (35KB): source + test + demo | 591K | 8.5 | class ✓ types ✓ tests ✓ docs ✓ |

修复前这两个任务 workspace 为空（Coder 在文本中输出代码但未调用 file_write）。

### HumanEval Benchmark

| Metric | Value |
|--------|-------|
| pass@1 | **148/164 (90.2%)** |
| Model | DeepSeek-chat |
| Time | 326s (164 tasks) |

### Coder Tool-Call Optimization (MCP mode, B1+B5+B6)

| Config | Total Tokens | Avg Score | Change |
|--------|-------------|-----------|--------|
| Baseline | 1,165K | 8.83 | — |
| Optimized prompt | 787K | 8.90 | **-32% tokens** |

### Key Findings

- **HumanEval 90.2% pass@1**: 通过公认 benchmark 验证系统代码生成能力
- **MCP 模式产出真正可运行的工程文件**: 源码 + 单元测试 + 集成 demo，workspace 文件验证通过
- **Coder prompt 优化降低 32% MCP token 消耗**: 减少冗余工具调用（重复 file_list/file_read），质量不变
- **单 Agent 会偷懒**: 无 Reviewer 时 B7 仅 227 token 输出，多 Agent 架构的质量门控必不可少
- **Prompt 工程 ROI 最高**: 一句 "同一模块方法合并" 让 Planner 拆分从 6→2 个，token 降 85%（400K→57K）
- **Coder-Reviewer 循环中的上下文维护至关重要**: 重试路径必须重新注入 workspace 状态，否则 Coder 退化为纯文本输出
- **100% 完成率**: 所有 8 个任务（含 3 个 hard）全部通过 score ≥ 7.0

## Project Structure

```
CodeAgent-MCP/
├── config/
│   ├── settings.yaml          # LLM provider 配置
│   ├── agents.yaml            # Agent prompt 与参数
│   └── mcp_servers.yaml       # MCP server 启用/配置
├── src/
│   ├── core/
│   │   ├── llm_client.py      # 统一 LLM 调用层 (OpenAI 兼容)
│   │   ├── agent_base.py      # Agent 基类 + ReAct 循环
│   │   ├── orchestrator.py    # 编排器 (Coder-Reviewer 循环)
│   │   └── config.py          # 配置加载
│   ├── agents/
│   │   ├── planner.py         # 任务拆解 Agent
│   │   ├── coder.py           # 代码生成 Agent (可注入 MCP)
│   │   └── reviewer.py        # 代码审查 Agent
│   ├── mcp/
│   │   ├── client.py          # MCP Client 管理器
│   │   └── servers/
│   │       ├── file_server.py # 文件操作 (路径安全校验)
│   │       ├── shell_server.py# Shell 执行 (白名单)
│   │       ├── git_server.py  # Git 操作
│   │       └── rag_server.py  # RAG 检索 (FAISS + MMR)
│   └── main.py                # CLI 入口
├── eval/
│   ├── benchmark_tasks.json   # 8 个评测任务
│   ├── run_eval.py            # 评测运行器
│   └── run_comparison.py      # 对比实验
├── app.py                     # HuggingFace Spaces Demo (Gradio)
├── tests/                     # 单元测试
└── notebooks/                 # Colab 验证记录
```

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| 自研框架，不用 LangChain | ~300 行，面试能讲清每一行逻辑 |
| Planner/Reviewer 不注入 MCP | 只有 Coder 需要工具，降低复杂度 |
| JSON 4 层容错解析 | LLM 输出格式不稳定，需要多层 fallback |
| Shell 白名单 | 只允许 python/pytest/ruff 等安全命令 |
| 文件路径安全校验 | 限制在 ALLOWED_ROOT 内，防止目录遍历 |
| 环境变量显式合并 | MCP 子进程需确保继承父进程 env |

## Project Series

本项目是四个递进项目的最终整合：

1. **[small-llms-tool-use](https://github.com/XIECHENG6/small-llms-tool-use)** — 小模型 function calling，QLoRA 微调达 86-89% exact match
2. **[agenttune](https://github.com/XIECHENG6/agenttune)** — 小模型多步 ReAct 推理，100% task success rate
3. **[smallrag](https://github.com/XIECHENG6/smallrag)** — RAG 最优配置研究，chunk_size=512 + MMR + top-k=5
4. **CodeAgent-MCP** (本项目) — 整合上述能力为 MCP 多 Agent 系统

## License

MIT
