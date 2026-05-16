"""
Git operations MCP Server.
Provides: git_status, git_diff, git_log, git_commit
Security: operates only within the configured repository root.
"""

import asyncio
import os

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("git-server")

REPO_ROOT = os.environ.get("GIT_SERVER_ROOT", os.getcwd())
MAX_OUTPUT = 20_000


async def _run_git(args: list[str]) -> tuple[str, int]:
    proc = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=REPO_ROOT,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
    output = stdout.decode("utf-8", errors="replace")
    if stderr:
        err = stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            output += f"\nSTDERR:\n{err}"
    return output[:MAX_OUTPUT], proc.returncode


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="git_status",
            description="查看当前仓库状态 (git status --short)",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="git_diff",
            description="查看文件变更 (git diff)，可指定文件路径",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "指定文件路径 (可选)", "default": ""},
                    "staged": {"type": "boolean", "description": "是否查看已暂存的变更", "default": False},
                },
                "required": [],
            },
        ),
        Tool(
            name="git_log",
            description="查看提交历史 (git log --oneline)",
            inputSchema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "显示条数", "default": 10},
                },
                "required": [],
            },
        ),
        Tool(
            name="git_commit",
            description="暂存所有变更并提交 (git add -A && git commit)",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "提交信息"},
                },
                "required": ["message"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "git_status":
            output, _ = await _run_git(["status", "--short"])
            return [TextContent(type="text", text=output or "(clean working tree)")]

        elif name == "git_diff":
            args = ["diff"]
            if arguments.get("staged"):
                args.append("--cached")
            path = arguments.get("path", "")
            if path:
                args.append("--")
                args.append(path)
            output, _ = await _run_git(args)
            return [TextContent(type="text", text=output or "(no changes)")]

        elif name == "git_log":
            count = min(arguments.get("count", 10), 50)
            output, _ = await _run_git(["log", f"--oneline", f"-{count}"])
            return [TextContent(type="text", text=output or "(no commits)")]

        elif name == "git_commit":
            message = arguments.get("message", "auto commit")
            await _run_git(["add", "-A"])
            output, code = await _run_git(["commit", "-m", message])
            if code != 0:
                return [TextContent(type="text", text=f"Commit failed:\n{output}")]
            return [TextContent(type="text", text=output)]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except asyncio.TimeoutError:
        return [TextContent(type="text", text="Git command timed out")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
