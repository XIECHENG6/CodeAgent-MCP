from ..core.agent_base import AgentBase
from ..core.llm_client import LLMClient


class CoderAgent(AgentBase):
    def __init__(self, config: dict, llm_client: LLMClient, mcp_manager=None):
        super().__init__(config, llm_client, mcp_manager)
        self.workspace_files: list[str] = []

    def set_workspace_files(self, files: list[str]):
        self.workspace_files = files

    def format_input(self, task) -> str:
        if isinstance(task, str):
            prompt = task
        elif isinstance(task, dict):
            desc = task.get("description", str(task))
            deps = task.get("dependencies", [])
            prompt = f"请完成以下任务:\n{desc}"
            if deps:
                prompt += f"\n\n依赖的前置任务: {', '.join(deps)}"
        else:
            prompt = str(task)

        if self.mcp and self.workspace_files:
            prompt += f"\n\nWorkspace 已有文件: {', '.join(self.workspace_files)}"
            prompt += "\n可以用 file_read 读取已有文件作为参考，然后直接 file_write 写入新文件。"
        elif self.mcp:
            prompt += "\n\nWorkspace 为空，请直接用 file_write 写入代码文件，不需要先 file_list。"

        return prompt
