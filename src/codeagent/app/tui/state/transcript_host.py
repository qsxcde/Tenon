"""Transcript mixin 宿主的类型声明基类。

``TranscriptLayoutMixin`` / ``ProgressiveTranscriptMixin`` 组合进
``Transcript`` 后通过 ``self`` 访问宿主属性;mypy 无法从 mixin 推断宿主成员,
故在此集中声明。本文件只含类级类型注解,不包含默认值、赋值或方法体。
单独成模块(而非与 TuiModelHost 同文件)以保持 app 导入图无环:
mixin → 本模块 → transcript_index,而 Transcript → mixin。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections import OrderedDict
    from collections.abc import Callable
    from typing import Any

    from ..presentation.primitives import Component, RichLine
    from .transcript_index import TranscriptLayoutIndex


class TranscriptHost:
    """Transcript 组合宿主的属性声明（TranscriptLayoutMixin / ProgressiveTranscriptMixin 共享）。"""

    # -- 块容器与滚动状态(Transcript.__init__ 建立) ------------------------
    _blocks: list[Component]
    follow: bool
    _scroll_top: int
    _line_blocks: list[Component | None]
    _new_output_count: int
    visible_range: tuple[int, int]
    overscan: int
    layout_index: list[tuple[int, int, Component]]
    _range_starts: list[int]
    overscan_range: tuple[int, int]
    _anchor: tuple[int, int] | None
    _restore_anchor: bool
    _last_width: int | None
    _last_block_count: int
    _last_total: int

    # -- 布局缓存状态 -----------------------------------------------------
    _cache_capacity: int
    _cache_line_capacity: int
    _max_width_variants: int
    _layout_cache: OrderedDict[tuple[int, int, int], list[RichLine]]
    cache_hits: int
    cache_misses: int
    _layout_index: TranscriptLayoutIndex
    layout_stats: dict[str, int]

    # -- Transcript 宿主方法(mixin 调用) ---------------------------------
    _restore_anchor_start: Callable[[int, int, int], int | None]
    _capture_anchor: Callable[[int], None]

    # -- TranscriptLayoutMixin 方法(ProgressiveTranscriptMixin 调用) -----
    _cache_key: Callable[[Any, int], tuple[int, int, int]]
    _cache_lookup: Callable[[Any, int], list[RichLine] | None]
    _cache_store: Callable[[Any, int, list[RichLine]], None]
    _render_cached: Callable[[Any, int], list[RichLine]]
    _cache_block: Callable[[Any, int], list[RichLine]]
    _geometry: Callable[[int, int, list[RichLine]], tuple[int, int, int]]
    _collect_visible: Callable[..., list[RichLine]]
