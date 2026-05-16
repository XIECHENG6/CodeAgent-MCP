import logging
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPManager:
    def __init__(self):
        self._exit_stack = AsyncExitStack()
        self.sessions: dict[str, ClientSession] = {}
        self.tools_registry: dict[str, dict] = {}

    async def connect_server(self, name: str, command: str, args: list[str], env: dict | None = None):
        params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(params)
        )
        read_stream, write_stream = stdio_transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await session.initialize()

        self.sessions[name] = session

        tools_response = await session.list_tools()
        for tool in tools_response.tools:
            self.tools_registry[tool.name] = {
                "server": name,
                "schema": tool.inputSchema,
                "description": tool.description or "",
            }

        logger.info(f"Connected to MCP server '{name}': {len(tools_response.tools)} tools")

    async def connect_from_config(self, config: dict):
        servers = config.get("servers", {})
        for name, server_config in servers.items():
            if not server_config.get("enabled", True):
                continue
            await self.connect_server(
                name=name,
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env"),
            )

    def get_openai_tools(self) -> list[dict]:
        tools = []
        for tool_name, info in self.tools_registry.items():
            tools.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": info["description"],
                    "parameters": info["schema"],
                },
            })
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        if tool_name not in self.tools_registry:
            raise ValueError(f"Unknown tool: '{tool_name}'. Available: {list(self.tools_registry.keys())}")

        server_name = self.tools_registry[tool_name]["server"]
        session = self.sessions[server_name]

        result = await session.call_tool(tool_name, arguments=arguments)

        texts = []
        for content in result.content:
            if hasattr(content, "text"):
                texts.append(content.text)
            else:
                texts.append(str(content))
        return "\n".join(texts)

    async def disconnect_all(self):
        await self._exit_stack.aclose()
        self.sessions.clear()
        self.tools_registry.clear()
        logger.info("All MCP servers disconnected")
