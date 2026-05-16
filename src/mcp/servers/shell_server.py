"""
Shell command execution MCP Server.
Provides: shell_exec
Security: only allows whitelisted commands and has timeout limits.
"""

import asyncio
import os
import shlex

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("shell-server")

TIMEOUT = 30  # seconds
MAX_OUTPUT = 10_000  # characters

ALLOWED_COMMANDS = {
    "python", "python3", "pip", "pytest", "ruff",
    "ls", "dir", "cat", "head", "tail", "wc",
    "echo", "pwd", "which", "find", "grep",
}

BLOCKED_PATTERNS = ["rm -rf", "sudo", "chmod 777", "> /dev", "mkfs", "dd if="]


def _validate_command(command: str) -> str | None:
    for pattern in BLOCKED_PATTERNS:
        if pattern in command:
            return f"Blocked: command contains dangerous pattern '{pattern}'"

    parts = shlex.split(command) if not os.name == "nt" else command.split()
    if parts:
        base_cmd = os.path.basename(parts[0])
        if base_cmd not in ALLOWED_COMMANDS:
            return f"Blocked: command '{base_cmd}' is not in the allowed list: {sorted(ALLOWED_COMMANDS)}"
    return None


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="shell_exec",
            description="执行 shell 命令并返回输出 (受限沙箱，仅允许安全命令)",
            inputSchema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "要执行的命令"},
                    "timeout": {"type": "integer", "description": "超时秒数", "default": 30},
                },
                "required": ["command"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name != "shell_exec":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    command = arguments.get("command", "")
    timeout = min(arguments.get("timeout", TIMEOUT), TIMEOUT)

    error = _validate_command(command)
    if error:
        return [TextContent(type="text", text=error)]

    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.environ.get("SHELL_SERVER_CWD", os.getcwd()),
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        output_parts = []
        if stdout:
            out_text = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT]
            output_parts.append(f"STDOUT:\n{out_text}")
        if stderr:
            err_text = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT]
            output_parts.append(f"STDERR:\n{err_text}")

        output_parts.append(f"\nExit code: {proc.returncode}")
        return [TextContent(type="text", text="\n".join(output_parts))]

    except asyncio.TimeoutError:
        return [TextContent(type="text", text=f"Command timed out after {timeout}s")]
    except Exception as e:
        return [TextContent(type="text", text=f"Execution error: {type(e).__name__}: {e}")]


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
