# 实验报告 03 — 对比实验与完整 Benchmark

> **Notebook**: `03_Experiments.ipynb`
> **日期**: 2026-05-16
> **目标**: 系统性对比 single-agent / multi-agent / MCP 三种配置的质量、效率和成本

---

## 实验 1: Ablation Study (B1, B4, B7)

### 结果

| 配置 | 完成率 | 平均分 | 平均 Token | 平均耗时 |
|------|--------|--------|-----------|----------|
| single_agent_nomcp | 3/3 | N/A (无 Reviewer) | 2,524 | 16.2s |
| multi_agent_nomcp | 3/3 | 8.6 | 10,821 | 50.4s |
| multi_agent_mcp | 3/3 | 8.8 | 390,426 | 379.4s |

### 按任务对比

| 任务 | Single Agent | Multi (no-mcp) | Multi (mcp) |
|------|-------------|----------------|-------------|
| B1 LRU Cache | 3.4K tok, 21s | score=9.2, 13.6K tok | score=9.2, 294K tok, 文件✅ |
| B4 CSV Analyzer | 4.0K tok, 26s | score=7.5, 4.7K tok | score=9.2, 129K tok, 文件✅ |
| B7 Config Manager | **227 tok, 1.6s** ⚠️ | score=9.0, 14.2K tok | score=8.0, 748K tok, **文件❌** |

### 发现

1. **Single Agent 的 B7 异常**: 仅 227 token、200 字符输出。没有 Planner 引导也没有 Reviewer 质量关卡，单 Agent 在某些任务上会"偷懒"给出极简响应
2. **B4 分数提升明显**: single/multi_nomcp 的 B4 都偏低(7.5)，但 MCP 模式达到 9.2——因为 Coder 能实际运行代码验证结果
3. **B7 在 MCP 模式 token 爆炸**: 748K tokens，workspace 为空。可能是 Coder 在工具调用上陷入了循环

---

## 实验 2: Full Benchmark (8 tasks, no-mcp)

### 结果汇总

| 指标 | 数值 |
|------|------|
| 完成率 | **8/8 (100%)** |
| 平均分 | **8.89/10** |
| 总 Token | 136,153 |
| 平均耗时 | 70.2s/task |

### 按任务详情

| 任务 | 难度 | 分数 | Token | 耗时 | 子任务 |
|------|------|------|-------|------|--------|
| B1 LRU Cache | medium | 9.5 | 14,347 | 56.5s | 2 |
| B2 BST | medium | 9.2 | 7,682 | 32.9s | 2 |
| B3 HTTP Retry | medium | 8.5 | 13,078 | 57.0s | 2 |
| B4 CSV Analyzer | easy | 9.2 | 15,391 | 66.9s | 3 |
| B5 Rate Limiter | hard | 9.2 | 15,136 | 72.8s | 3 |
| B6 Markdown Parser | hard | 8.5 | 17,336 | 59.9s | 2 |
| B7 Config Manager | easy | 8.5 | 17,139 | 73.3s | 3 |
| B8 Async Task Queue | hard | 8.5 | 36,044 | 142.4s | 3 |

### 按难度分组

| 难度 | 任务数 | 平均分 | 平均 Token |
|------|--------|--------|-----------|
| easy | 2 | 8.85 | 16,265 |
| medium | 3 | 9.07 | 11,702 |
| hard | 3 | 8.73 | 22,839 |

### 发现

1. **100% 完成率**: 所有 8 个任务全部通过（score ≥ 7.0），包括 hard 级别
2. **medium 反而最高分**: 可能因为 medium 任务（LRU/BST/HTTP）有明确的"标准答案"，LLM 训练数据中见过很多
3. **B8 Token 最高 (36K)**: 异步任务队列是最复杂的任务，Planner 拆了 3 个子任务，Coder-Reviewer 循环了多轮
4. **所有任务都有 type hints + docstring + tests**: code_checks 全部为 true，说明 Reviewer 确实在推动代码规范

---

## 实验 3: Full Benchmark + MCP (8 tasks)

### 结果汇总

| 指标 | no-mcp | mcp | 变化 |
|------|--------|-----|------|
| 完成率 | 8/8 | **8/8** | 相同 |
| 平均分 | 8.89 | **8.95** | +0.06 |
| 总 Token | 136K | **3,035K** | **×22** |
| 平均耗时 | 70s | **379s** | ×5.4 |

### 按任务对比 (no-mcp vs mcp)

| 任务 | no-mcp 分数 | mcp 分数 | Token 倍率 | 产出文件 |
|------|------------|---------|-----------|----------|
| B1 LRU Cache | 9.5 | 9.2 | ×9.5 | lru_cache.py, test_lru_cache.py |
| B2 BST | 9.2 | 9.2 | ×39 | binary_search_tree.py, test_*.py |
| B3 HTTP Retry | 8.5 | 8.8 | ×34 | retry_client.py, pytest.ini, test_*.py |
| B4 CSV Analyzer | 9.2 | 8.5 | ×28 | csv_analyzer.py, test_*.py |
| B5 Rate Limiter | 9.2 | 9.2 | ×15 | rate_limiter.py, test_*.py |
| B6 Markdown Parser | 8.5 | 9.2 | ×12 | markdown_parser.py, test_*.py |
| B7 Config Manager | 8.5 | 8.5 | ×35 | **空** ⚠️ |
| B8 Async Task Queue | 8.5 | 9.0 | ×19 | **空** ⚠️ |

### 发现

1. **MCP 模式分数略高但 token 成本 22 倍**: 质量提升不显著 (+0.06)，但 Coder 能产出真正可运行的工程产物（源码 + 测试文件）
2. **B7 和 B8 的 workspace 仍为空**: 这两个任务在 MCP 模式下 token 最高 (606K, 685K)，可能是 Coder 在 10 轮工具调用内未能完成文件写入，最终 fallback 到纯文本输出
3. **B3 额外产出了 pytest.ini**: 说明 Coder 会根据测试需要自主创建配置文件，展现了 Agent 的自主性
4. **code_checks 在 MCP 模式不准确**: 因为 `analyze_code_output()` 分析的是 Coder 的文本回复而非 workspace 文件。MCP 模式下代码在文件里，回复只是总结

---

## 核心结论

### 多 Agent 架构的价值

```
                质量    成本    产出物
single_agent:   低      极低    纯文本代码块
multi_nomcp:    高      中      纯文本代码块(高质量)
multi_mcp:      高      高      可运行的工程文件
```

**最佳实践**: 如果只需要代码片段（面试题、算法练习），用 **multi_agent_nomcp**（性价比最高）。如果需要完整工程产物（写文件、跑测试、检查风格），用 **multi_agent_mcp**。

### 待优化项

1. **MCP token 成本过高**: Coder 每次都先 `file_list` → `file_search` → `file_read`，大量冗余调用。可优化 Coder prompt 减少探索行为
2. **B7/B8 workspace 空**: `max_tool_rounds=10` 可能不够复杂任务使用，或需要给 Coder 更明确的"先写文件"指令
3. **code_checks 修复**: MCP 模式下应读取 workspace 文件做代码质量检查，而非分析文本回复

---

## 学到了什么

1. **"加工具"不一定提升质量，但改变了产出形态**: no-mcp 和 mcp 分数几乎相同 (8.89 vs 8.95)，但 mcp 产出的是真正的文件系统工程产物
2. **成本与能力的 trade-off 是系统设计的核心问题**: 22× token 成本换来的是"代码真的写入了文件并通过了测试"——这在生产环境中是必要的，在评测中不一定
3. **单 Agent 会偷懒**: B7 仅 227 token 的输出说明没有 Reviewer 质量门控，LLM 可能给出 minimal effort 的回复
4. **评测指标要匹配评测目的**: `code_checks` 在 MCP 模式下失效，暴露了评测框架的局限——评测工具本身也需要迭代
