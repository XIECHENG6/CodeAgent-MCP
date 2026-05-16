import os
import json
import logging
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: dict):
        self.client = AsyncOpenAI(
            api_key=config.get("api_key") or os.getenv("OPENAI_API_KEY"),
            base_url=config.get("base_url", "https://api.deepseek.com"),
        )
        self.model = config.get("model", "deepseek-chat")
        self.temperature = config.get("temperature", 0.5)
        self.max_tokens = config.get("max_tokens", 4096)

    @classmethod
    def from_settings(cls, provider: str = "default", settings: dict | None = None) -> "LLMClient":
        if settings is None:
            from .config import load_settings
            settings = load_settings()
        provider_config = settings["providers"][provider]
        return cls(provider_config)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str = "auto",
        temperature: float | None = None,
    ) -> dict:
        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        result = {
            "content": choice.message.content or "",
            "tool_calls": [],
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                arguments = self._safe_parse_arguments(tc.function.arguments)
                result["tool_calls"].append({
                    "id": tc.id,
                    "function": tc.function.name,
                    "arguments": arguments,
                })

        logger.debug(
            f"LLM call: model={self.model}, "
            f"tokens={result['usage']['prompt_tokens']}+{result['usage']['completion_tokens']}"
        )
        return result

    def _safe_parse_arguments(self, raw: str) -> dict:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            import re
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.warning(f"Failed to parse tool arguments: {raw[:200]}")
            return {"_raw": raw}
