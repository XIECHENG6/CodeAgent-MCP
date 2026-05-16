# 实验报告 02 — MCP 端到端验证

> **Notebook**: `02_MCP_E2E_Test.ipynb`
> **日期**: 2026-05-16 (共迭代 3 次)
> **目标**: 验证 use_mcp=True 模式下 Coder Agent 能否通过 MCP 工具真正写出文件

---

## 实验内容

| 测试项 | 结果 |
|--------|------|
| file_server MCP 连接 (4 工具) | ✅ 路径安全拦截生效 |
| shell_server MCP 连接 (1 工具) | ✅ `rm -rf /` 被白名单拒绝 |
| git_server MCP 连接 (4 工具) | ✅ 首次验证 |
| use_mcp=True 端到端 | ✅ 第 3 次迭代通过 |
| 评测框架单任务试跑 | ✅ B1 LRU Cache score=9.2 |

## 迭代过程（这是本实验的核心价值）

### 第 1 次运行 — 发现两个 bug

| 指标 | 数值 |
|------|------|
| Planner 拆分 | 6 个子任务 (过度拆分) |
| Token 消耗 | 400,483 |
| Workspace 文件 | **空** (路径 bug) |

**问题 1: Planner 过度拆分**
简单的 Stack 任务被拆成 6 个子任务（init、push、pop、peek、is_empty、测试），每个子任务独立 ReAct 循环。

**问题 2: file_server 路径解析**
`_safe_path()` 用 `Path(path).resolve()` 从 CWD 解析，Coder 传 `"stack.py"` 时文件写到了项目目录而非 workspace。

### 第 2 次运行 — Planner 优化生效，workspace 仍空

修复了 Planner prompt（"2-4 个子任务"、"同一模块方法合并"）和 `_safe_path`。

| 指标 | 第1次 → 第2次 | 变化 |
|------|--------------|------|
| 任务拆分 | 6 → 2 | -67% |
| Token | 400K → 57K | **-85%** |
| Score | 8.92 → 9.25 | +0.33 |
| Workspace | 空 → 空 | 未解决 |

**根因分析**: `MCPManager.connect_server` 传 `env=None` 给 `StdioServerParameters`，MCP SDK 未可靠继承父进程环境变量。

### 第 3 次运行 — 全部通过

修复了 `MCPManager` 显式合并 `{**os.environ, **(env or {})}`，同时设置 `SHELL_SERVER_CWD` 和 `GIT_SERVER_ROOT`。

| 指标 | 最终结果 |
|------|----------|
| 任务拆分 | 2 个 |
| Token | 59,311 |
| Score | 9.35 avg (9.2 + 9.5) |
| Workspace | **stack.py + test_stack.py** ✅ |
| 代码质量 | 泛型 `Generic[T]`、ruff 通过、26 个 pytest 用例 |

## 关键发现

1. **Prompt 工程对成本影响巨大**: 一句 "同一模块方法合并" 让 token 降 85%，这比任何代码优化都有效
2. **环境变量在子进程链中容易丢失**: MCP Client → stdio → Server 是三层进程，env 传递需要显式保证
3. **所有 MCP server 需共享 workspace**: file_server 写文件、shell_server 跑测试、git_server 查 diff，三者必须在同一目录工作

## 学到了什么

- 调试多进程系统时，最有效的方法是"逐层验证"——先验证 MCP Server 单独可用，再验证 Client 连接，最后验证 Agent 调用
- 性能优化的第一步永远是"减少不必要的工作"，而不是"让每步更快"
- 评测框架的稳定性很重要——B1 跑了两次 (12066 vs 11957 tokens, 9.2 vs 9.2 score)，结果高度一致
