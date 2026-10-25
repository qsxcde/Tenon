"""应用组合根导出入口。

实现按职责位于 :mod:`tenon.app.composition`，本模块只导出组合根 API。
跨层装配实现不得反向导入本 façade。
"""

from __future__ import annotations

from tenon.app.composition.model.factory import (
    ChatModelPort,
    LlmSummarizer,
    _usage_of as _usage_of,
)
from tenon.app.composition.policy import _create_policy as _create_policy
from tenon.app.composition.prompts import (
    _build_system_prompt as _build_system_prompt,
    agents_sources,
    skills_view,
)
from tenon.app.composition.runtime.factory import (
    AgentRuntime,
    _LazyConfig as _LazyConfig,
    _LazySummarizer as _LazySummarizer,
    close_runtime_for_config,
    close_runtime_for_config_async,
    create_agent_config,
    create_agent_runtime,
    runtime_for_config,
)
from tenon.app.composition.runtime.extensions import (
    RuntimeExtensions,
    normalize_runtime_extensions,
)
from tenon.app.composition.session.factory import (
    create_agent_session,
    create_session_manager,
)
from tenon.app.composition.tools.factory import create_tools
from tenon.app.composition.tui.factory import (
    TuiAssembler,
    create_tui_app,
)

__all__ = [
    "AgentRuntime",
    "RuntimeExtensions",
    "ChatModelPort",
    "LlmSummarizer",
    "TuiAssembler",
    "create_agent_config",
    "create_agent_runtime",
    "create_agent_session",
    "create_session_manager",
    "create_tools",
    "create_tui_app",
    "normalize_runtime_extensions",
    "runtime_for_config",
    "close_runtime_for_config",
    "close_runtime_for_config_async",
    "agents_sources",
    "skills_view",
]
