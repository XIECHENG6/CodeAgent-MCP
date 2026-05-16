from ..core.agent_base import AgentBase
from ..core.llm_client import LLMClient


class PlannerAgent(AgentBase):
    def __init__(self, config: dict, llm_client: LLMClient):
        super().__init__(config, llm_client, mcp_manager=None)

    def format_input(self, task) -> str:
        if isinstance(task, str):
            return task
        return f"请分析以下开发需求并拆解为子任务：\n\n{task}"
