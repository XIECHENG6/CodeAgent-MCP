# 实验报告 01 — 环境验证与基础流程

> **Notebook**: `01_Verify_Setup.ipynb`
> **日期**: 2026-05-16
> **目标**: 验证 Colab 环境、API 连通性、基础多 Agent 流程

---

## 实验内容

| 步骤 | 验证项 | 结果 |
|------|--------|------|
| 1 | Google Drive 挂载 + 代码加载 | ✅ 通过 |
| 2 | DeepSeek API 连通 | ✅ 返回 "Hello! How can I" |
| 3 | use_mcp=False 端到端 (LRU Cache) | ✅ Planner→Coder→Reviewer 循环正常 |
| 4 | pytest 单元测试 | ✅ 5/5 通过 |
| 5 | MCP file_server 连接 | ✅ 4 个工具列出 |

## 关键发现

1. **基础流程可行**: Planner 拆解 → Coder 生成 → Reviewer 评分，闭环跑通
2. **MCP + Jupyter 不兼容**: Jupyter 的虚拟 IO 没有 `fileno()`，MCP stdio 传输会崩溃
   - **解法**: 所有 MCP 操作封装为独立 `.py` 脚本，通过 `!python script.py` 运行
3. **MCP SDK API 变化**: `server.run()` 需要第三个参数 `initialization_options`
4. **API Key 传递问题**: Colab Secrets 只能在 notebook cell 访问，独立脚本需要通过 `/tmp/.api_key` 文件传递

## 学到了什么

- MCP 协议的 stdio 传输模式对运行环境有要求，不是所有 Python 环境都支持
- Colab 上的解决思路是"进程隔离"——主进程管 notebook 交互，子进程管 MCP 通信
- DeepSeek API 兼容 OpenAI 格式，用 `openai` 库 + 自定义 `base_url` 即可调用

## 遗留问题

- use_mcp=True 尚未验证（Coder 还没真正用工具写文件）
- 需要确认 MCP 工具调用在 Coder Agent 的 ReAct 循环中是否正常
