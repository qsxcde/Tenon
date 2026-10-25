"""工具注册表:声明式登记原子工具,make_tools(cfg) 按注册项装配工具集。

组合根调用 make_tools 取得具体原子工具,再由 `app/composition/tools/adapter.py`
转换为可交给自研循环的 AgentTool 列表。注册表即注入点:
cwd 注入全部工具(design D2;对应 spec「装配时注入工作目录」),技能注册表
(名 → 渲染块)注入 ``skill`` 工具(design skills-system D3,组合根预渲染)。

数据化要点:新增工具 = 在 ``BUILTIN_TOOL_SPECS`` 追加一条 ``ToolSpec`` 声明
(名称 + 构建函数),装配顺序即声明顺序;``ToolRegistry`` 对重复名称 fail-closed,
保证工具名稳定唯一(对应 spec「工具注册与装配」的固定名称契约)。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from tenon.tools.atomic import (
    BashTool,
    EditTool,
    FindTool,
    GrepTool,
    LsTool,
    ReadTool,
    SkillTool,
    TodoTool,
    WebFetchTool,
    WebSearchTool,
    WriteTool,
)
from tenon.tools.base import AtomicTool
from tenon.tools.execution.sandbox import SANDBOX_DANGER_FULL_ACCESS
from tenon.tools.shared import CheckpointStore, ToolResourceLimits

__all__ = [
    "BUILTIN_TOOL_SPECS",
    "ToolBuildContext",
    "ToolFactory",
    "ToolRegistry",
    "ToolSpec",
    "builtin_tool_registry",
    "make_tools",
]


@dataclass(frozen=True, slots=True)
class ToolBuildContext:
    """一次工具装配的注入上下文(cwd / 技能注册表 / 资源限制 / 沙箱策略)。"""

    cwd: str | None
    skills: dict[str, str] | None
    resource_limits: ToolResourceLimits
    #: bash 执行沙箱策略;默认保持原行为(danger-full-access)。
    sandbox_policy: str = SANDBOX_DANGER_FULL_ACCESS
    #: 写/编辑前快照存储;None = 不记录 checkpoint。
    checkpoint_store: CheckpointStore | None = None


#: 工具构建函数:由注册项把注入上下文转换为一个原子工具实例。
ToolFactory = Callable[[ToolBuildContext], AtomicTool]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """一条工具注册项:稳定名称 + 构建函数。"""

    name: str
    build: ToolFactory


class ToolRegistry:
    """有序工具注册表(name → ToolSpec);重复名称注册 fail-closed。"""

    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        self._specs: dict[str, ToolSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: ToolSpec) -> None:
        """登记一条注册项;名称冲突时抛出明确错误,不静默覆盖。"""
        if spec.name in self._specs:
            raise ValueError(f"工具名称重复注册: {spec.name}")
        self._specs[spec.name] = spec

    def names(self) -> tuple[str, ...]:
        """按注册顺序返回工具名。"""
        return tuple(self._specs)

    def build(self, context: ToolBuildContext) -> list[AtomicTool]:
        """按注册顺序装配全部工具,每个工具共享同一注入上下文。"""
        return [spec.build(context) for spec in self._specs.values()]


def _standard_tool(cls: type[AtomicTool]) -> ToolFactory:
    """标准工具构建器:仅注入 cwd 与资源限制。"""

    def build(context: ToolBuildContext) -> AtomicTool:
        return cls(cwd=context.cwd, resource_limits=context.resource_limits)

    return build


def _skill_tool(context: ToolBuildContext) -> AtomicTool:
    """skill 工具构建器:额外注入组合根预渲染的技能注册表。"""
    return SkillTool(
        cwd=context.cwd,
        skills=context.skills,
        resource_limits=context.resource_limits,
    )


def _bash_tool(context: ToolBuildContext) -> AtomicTool:
    """bash 工具构建器:注入沙箱策略(受限策略无后端时执行期 fail-closed)。"""
    return BashTool(
        cwd=context.cwd,
        resource_limits=context.resource_limits,
        sandbox_policy=context.sandbox_policy,
    )


def _checkpointed_tool(cls: Any) -> ToolFactory:
    """写类工具构建器:注入 checkpoint 存储(None = 不记录快照)。"""

    def build(context: ToolBuildContext) -> AtomicTool:
        return cls(
            cwd=context.cwd,
            resource_limits=context.resource_limits,
            checkpoint=context.checkpoint_store,
        )

    return build


#: 内建工具声明;顺序即 make_tools 产出顺序(read → todo),契约由测试锁定。
BUILTIN_TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("read", _standard_tool(ReadTool)),
    ToolSpec("write", _checkpointed_tool(WriteTool)),
    ToolSpec("edit", _checkpointed_tool(EditTool)),
    ToolSpec("bash", _bash_tool),
    ToolSpec("grep", _standard_tool(GrepTool)),
    ToolSpec("find", _standard_tool(FindTool)),
    ToolSpec("ls", _standard_tool(LsTool)),
    ToolSpec("skill", _skill_tool),
    ToolSpec("web_fetch", _standard_tool(WebFetchTool)),
    ToolSpec("web_search", _standard_tool(WebSearchTool)),
    ToolSpec("todo", _standard_tool(TodoTool)),
)


def builtin_tool_registry() -> ToolRegistry:
    """返回一份新的内建工具注册表(不共享可变全局注册状态)。"""
    return ToolRegistry(BUILTIN_TOOL_SPECS)


def make_tools(
    cfg: Any = None,
    skills: dict[str, str] | None = None,
    resource_limits: ToolResourceLimits | None = None,
) -> list[AtomicTool]:
    """按配置装配工具集,返回自研原子工具列表。

    - ``cfg`` 预留配置;若提供 ``cwd`` 字段则作为全部工具的工作目录,
      否则回退进程启动目录(P2-8);
    - ``skills`` 为技能名 → 渲染块 注册表(组合根预渲染;None = skill 工具
      返回"未注入"提示);
    - 默认包含 read / write / edit / bash / grep / find / ls / skill /
      web_fetch / web_search / todo 十一个工具,声明见 ``BUILTIN_TOOL_SPECS``;
    - 无网络、无密钥副作用(web 工具的网络能力经注入,缺省实现不主动出网)。
    """
    cwd = getattr(cfg, "cwd", None) if cfg is not None else None
    limits = resource_limits or ToolResourceLimits.from_config(cfg)
    sandbox_policy = (
        getattr(cfg, "sandbox_policy", SANDBOX_DANGER_FULL_ACCESS) or SANDBOX_DANGER_FULL_ACCESS
    )
    checkpoint_store = _resolve_checkpoint_store(cfg)
    context = ToolBuildContext(
        cwd=cwd,
        skills=skills,
        resource_limits=limits,
        sandbox_policy=str(sandbox_policy),
        checkpoint_store=checkpoint_store,
    )
    return builtin_tool_registry().build(context)


def _resolve_checkpoint_store(cfg: Any) -> CheckpointStore | None:
    """按配置构造 checkpoint 存储;未启用或缺目录时不记录快照。"""
    if not getattr(cfg, "checkpoints_enabled", False):
        return None
    root = getattr(cfg, "checkpoints_root", None)
    if root is None:
        return None
    return CheckpointStore(root)
