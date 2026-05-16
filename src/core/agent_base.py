import json
import logging
from abc import ABC, abstractmethod

from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class AgentBase(ABC):
    def __init__(self, config: dict, llm_client: LLMClient, mcp_manager=None):
        self.name = config["name"]
        self.system_prompt = config["system_prompt"]
        self.llm = llm_client
        self.mcp = mcp_manager
        self.max_tool_rounds = config.get("max_tool_rounds", 5)
        self.conversation: list[dict] = []
        self.total_tokens_used = 0

    async def run(self, user_input: str) -> str:
        self.conversation = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_input},
        ]

        tools = self.mcp.get_openai_tools() if self.mcp else None

        for round_idx in range(self.max_tool_rounds):
            response = await self.llm.chat(
                messages=self.conversation,
                tools=tools,
            )
            self.total_tokens_used += (
                response["usage"]["prompt_tokens"] + response["usage"]["completion_tokens"]
            )

            if not response["tool_calls"]:
                return response["content"]

            assistant_msg = {"role": "assistant", "content": response["content"]}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["function"],
                        "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                    },
                }
                for tc in response["tool_calls"]
            ]
            self.conversation.append(assistant_msg)

            for tc in response["tool_calls"]:
                tool_result = await self._execute_tool(tc["function"], tc["arguments"])
                self.conversation.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

            logger.info(f"[{self.name}] Round {round_idx + 1}: "
                        f"called {[tc['function'] for tc in response['tool_calls']]}")

        self.conversation.append({
            "role": "user",
            "content": "你已达到最大工具调用轮次，请基于当前进度给出最终回答。",
        })
        response = await self.llm.chat(messages=self.conversation)
        return response["content"]

    async def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        if not self.mcp:
            return f"Error: No MCP manager available to execute tool '{tool_name}'"
        try:
            result = await self.mcp.call_tool(tool_name, arguments)
            return str(result)
        except Exception as e:
            logger.error(f"[{self.name}] Tool '{tool_name}' failed: {e}")
            return f"工具调用失败: {type(e).__name__}: {str(e)}"

    @abstractmethod
    def format_input(self, task) -> str:
        pass
