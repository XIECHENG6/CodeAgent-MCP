from ..core.agent_base import AgentBase
from ..core.llm_client import LLMClient


class ReviewerAgent(AgentBase):
    def __init__(self, config: dict, llm_client: LLMClient):
        super().__init__(config, llm_client, mcp_manager=None)

    def format_input(self, task) -> str:
        if isinstance(task, dict) and "task" in task and "code" in task:
            task_info = task["task"]
            code = task["code"]
            desc = task_info.get("description", str(task_info)) if isinstance(task_info, dict) else str(task_info)
            return (
                f"任务需求: {desc}\n\n"
                f"Coder 的输出:\n{code}\n\n"
                f"请审查代码质量并给出评分。"
            )
        return f"请审查以下代码:\n\n{task}"
