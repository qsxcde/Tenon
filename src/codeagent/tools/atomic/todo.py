"""todo 原子工具:维护会话级任务清单(整体替换式更新)。

设计(design web-todo-tools D1):
- 状态经 ``TodoState`` 注入(缺省新建),工具不读配置、不跨层;
- 整体替换语义:模型一次提交完整清单,状态永远可由单次调用重建,
  幂等且无增量失同步;
- 状态仅驻内存:任务清单是工作过程视图,不进入会话持久化格式。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from codeagent.tools.base import AtomicTool

__all__ = ["MAX_TODOS", "TodoItem", "TodoState", "TodoTool"]

#: 单次清单条目上限:防止无界清单占用内存。
MAX_TODOS = 200

TodoStatus = Literal["pending", "in_progress", "done"]

_STATUS_MARKS: dict[str, str] = {
    "pending": "[ ]",
    "in_progress": "[~]",
    "done": "[x]",
}


class TodoItem(BaseModel):
    id: str = Field(min_length=1, description="稳定任务 ID(同一任务跨次调用保持不变)")
    content: str = Field(min_length=1, description="任务描述")
    status: TodoStatus = Field(description="pending / in_progress / done")


class TodoArgs(BaseModel):
    todos: list[TodoItem] = Field(description="完整任务清单(整体替换当前清单);空列表 = 清空")


class TodoState:
    """会话级任务清单状态;由组合根或工具缺省创建并注入。"""

    def __init__(self) -> None:
        self._items: tuple[TodoItem, ...] = ()

    def replace(self, items: tuple[TodoItem, ...]) -> None:
        self._items = items

    def items(self) -> tuple[TodoItem, ...]:
        return self._items


class TodoTool(AtomicTool[TodoArgs]):
    name = "todo"
    description = "维护任务清单:提交完整清单整体替换当前状态,返回最新清单。"
    Args = TodoArgs

    def __init__(
        self,
        cwd=None,
        ops=None,
        resource_limits=None,
        state: TodoState | None = None,
    ) -> None:
        super().__init__(cwd=cwd, ops=ops, resource_limits=resource_limits)
        self._state = state if state is not None else TodoState()

    def _invoke(self, args: TodoArgs) -> str:
        if len(args.todos) > MAX_TODOS:
            raise ValueError(f"任务条目超限: 最多 {MAX_TODOS} 条,收到 {len(args.todos)} 条")
        ids = [item.id for item in args.todos]
        if len(set(ids)) != len(ids):
            raise ValueError("任务 ID 不唯一: 请为每个任务分配唯一 id")
        self._state.replace(tuple(args.todos))
        return self._render()

    def _render(self) -> str:
        items = self._state.items()
        if not items:
            return "(任务清单为空)"
        lines = [f"{_STATUS_MARKS[item.status]} {item.id}: {item.content}" for item in items]
        counts = {
            status: sum(1 for item in items if item.status == status)
            for status in ("pending", "in_progress", "done")
        }
        lines.append(
            f"[共 {len(items)} 项: {counts['pending']} 待办 / "
            f"{counts['in_progress']} 进行中 / {counts['done']} 完成]"
        )
        return "\n".join(lines)
