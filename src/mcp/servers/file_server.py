"""
File operations MCP Server.
Provides: file_read, file_write, file_list, file_search
"""

import os
import glob as glob_module
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("file-server")

ALLOWED_ROOT = os.environ.get("FILE_SERVER_ROOT", os.getcwd())
MAX_FILE_SIZE = 100_000  # 100KB


def _safe_path(path: str) -> Path:
    root = Path(ALLOWED_ROOT).resolve()
    resolved = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
    if not str(resolved).startswith(str(root)):
        raise PermissionError(f"Access denied: path '{path}' is outside allowed root")
    return resolved


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="file_read",
            description="读取指定路径的文件内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径(相对于工作目录)"}
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="file_write",
            description="将内容写入指定路径的文件(自动创建目录)",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "文件内容"},
                },
                "required": ["path", "content"],
            },
        ),
        Tool(
            name="file_list",
            description="列出目录中的文件和子目录",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "目标目录", "default": "."},
                    "max_depth": {"type": "integer", "description": "最大递归深度", "default": 2},
                },
                "required": [],
            },
        ),
        Tool(
            name="file_search",
            description="在目录中搜索匹配模式的文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "搜索起始目录", "default": "."},
                    "pattern": {"type": "string", "description": "glob模式，如 *.py 或 **/*.js"},
                },
                "required": ["pattern"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "file_read":
            return [TextContent(type="text", text=_handle_read(arguments))]
        elif name == "file_write":
            return [TextContent(type="text", text=_handle_write(arguments))]
        elif name == "file_list":
            return [TextContent(type="text", text=_handle_list(arguments))]
        elif name == "file_search":
            return [TextContent(type="text", text=_handle_search(arguments))]
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
    except PermissionError as e:
        return [TextContent(type="text", text=f"Permission denied: {e}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


def _handle_read(args: dict) -> str:
    path = _safe_path(args["path"])
    if not path.exists():
        return f"File not found: {args['path']}"
    if path.stat().st_size > MAX_FILE_SIZE:
        return f"File too large ({path.stat().st_size} bytes, max {MAX_FILE_SIZE})"
    return path.read_text(encoding="utf-8")


def _handle_write(args: dict) -> str:
    path = _safe_path(args["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(args["content"], encoding="utf-8")
    return f"Written {len(args['content'])} bytes to {args['path']}"


def _handle_list(args: dict) -> str:
    directory = args.get("directory", ".")
    max_depth = args.get("max_depth", 2)
    root = _safe_path(directory)
    if not root.is_dir():
        return f"Not a directory: {directory}"

    lines = []
    _tree(root, root, lines, max_depth, 0)
    return "\n".join(lines) if lines else "(empty directory)"


def _tree(base: Path, current: Path, lines: list, max_depth: int, depth: int):
    if depth > max_depth:
        return
    try:
        entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return
    for entry in entries[:50]:  # limit entries per directory
        rel = entry.relative_to(base)
        prefix = "  " * depth
        if entry.is_dir():
            lines.append(f"{prefix}{rel.name}/")
            _tree(base, entry, lines, max_depth, depth + 1)
        else:
            size = entry.stat().st_size
            lines.append(f"{prefix}{rel.name} ({size}B)")


def _handle_search(args: dict) -> str:
    directory = args.get("directory", ".")
    pattern = args["pattern"]
    root = _safe_path(directory)

    search_pattern = str(root / pattern)
    matches = glob_module.glob(search_pattern, recursive=True)
    matches = matches[:30]  # limit results

    if not matches:
        return f"No files matching '{pattern}' in '{directory}'"

    root_str = str(root)
    results = []
    for m in matches:
        rel = os.path.relpath(m, root_str)
        results.append(rel)
    return "\n".join(results)


async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
