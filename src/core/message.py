from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class AgentType(Enum):
    PLANNER = "planner"
    CODER = "coder"
    REVIEWER = "reviewer"


@dataclass
class Message:
    role: Role
    content: str
    tool_call_id: Optional[str] = None
    name: Optional[str] = None


@dataclass
class TaskItem:
    task_id: str
    description: str
    status: str = "pending"
    dependencies: list[str] = field(default_factory=list)
    result: Optional[str] = None


@dataclass
class ReviewResult:
    score: float
    passed: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    summary: str = ""
