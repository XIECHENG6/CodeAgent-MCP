"""Basic tests for LLM client — requires API key to run."""

import os
import pytest
from src.core.llm_client import LLMClient


@pytest.fixture
def llm():
    return LLMClient({
        "api_key": os.getenv("OPENAI_API_KEY"),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "temperature": 0.3,
        "max_tokens": 100,
    })


@pytest.mark.asyncio
async def test_basic_chat(llm):
    response = await llm.chat(
        messages=[{"role": "user", "content": "Say hello in one word."}]
    )
    assert response["content"]
    assert "usage" in response
    assert response["usage"]["completion_tokens"] > 0


@pytest.mark.asyncio
async def test_tool_calling(llm):
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather for a city",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "City name"}
                    },
                    "required": ["city"],
                },
            },
        }
    ]
    response = await llm.chat(
        messages=[{"role": "user", "content": "What's the weather in Tokyo?"}],
        tools=tools,
    )
    assert response["tool_calls"]
    assert response["tool_calls"][0]["function"] == "get_weather"
    assert "city" in response["tool_calls"][0]["arguments"]


@pytest.mark.asyncio
async def test_safe_parse_arguments(llm):
    result = llm._safe_parse_arguments('{"city": "Tokyo"}')
    assert result == {"city": "Tokyo"}

    result = llm._safe_parse_arguments('invalid json {city: Tokyo}')
    assert "_raw" in result
