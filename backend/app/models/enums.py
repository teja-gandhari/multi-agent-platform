from enum import Enum

class ProjectStatus(str,Enum):
    CREATED="created"
    PLANNING="planning"
    RUNNING="running"
    COMPLETED="completed"
    FAILED="failed"

class TaskStatus(str,Enum):
    PENDING="pending"
    IN_PROGRESS="in_progress"
    COMPLETED="completed"
    FAILED="failed"

class TaskPriority(str,Enum):
    LOW="low"
    MEDIUM="medium"
    HIGH="high"
    CRITICAL="critical"

class AgentType(str, Enum):
    PLANNER = "planner"
    RESEARCHER = "researcher"
    DEVELOPER="developer"
    CODER = "coder"
    TESTER = "tester"
    REVIEWER = "reviewer"

class AgentStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"