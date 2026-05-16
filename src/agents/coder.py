from ..core.agent_base import AgentBase
from ..core.llm_client import LLMClient


class CoderAgent(AgentBase):
    def __init__(self, config: dict, llm_client: LLMClient, mcp_manager=None):
        super().__init__(config, llm_client, mcp_manager)

    def format_input(self, task) -> str:
        if isinstance(task, str):
            return task
        if isinstance(task, dict):
            desc = task.get("description", str(task))
            deps = task.get("dependencies", [])
            prompt = f"请完成以下任务:\n{desc}"
            if deps:
                prompt += f"\n\n依赖的前置任务: {', '.join(deps)}"
            return prompt
        return str(task)
