"""会话层:有状态会话壳、事件总线与会话生命周期管理器。

分层约束:session 不 import ai / tools / config,仅依赖 core 与 bus。
"""

from tenon.session.events.bus import EventBus
from tenon.session.compaction import CompactionPolicyConfig
from tenon.session.manager import SessionManager
from tenon.session.session import AgentSession

__all__ = ["AgentSession", "CompactionPolicyConfig", "EventBus", "SessionManager"]
