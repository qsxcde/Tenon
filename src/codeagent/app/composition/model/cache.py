"""上下文缓存观测与稳定前缀诊断。

provider 的 prompt cache 只在请求前缀稳定时命中;本模块提供两件纯函数能力:
1. 聚合 usage 中的 ``cached_tokens`` 得到命中率与诊断码;
2. 检测提示词前缀里的易变标记(时间戳、临时目录),帮助保持前缀可缓存。
不负责开启 provider 侧缓存(那由 provider/API 形状决定)。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "CACHE_COLD",
    "CACHE_EFFECTIVE",
    "CACHE_UNKNOWN",
    "CacheObservation",
    "is_cache_friendly_prefix",
    "volatile_prefix_markers",
]

CACHE_UNKNOWN = "cache_unknown"
CACHE_COLD = "cache_cold"
CACHE_EFFECTIVE = "cache_effective"

#: 易变标记:ISO 时间戳与临时目录(进入系统提示词前缀会让缓存永远不命中)。
_VOLATILE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}"),
    re.compile(r"/tmp/|/var/folders/|\\\\AppData\\\\Local\\\\Temp"),
)

#: 默认达到多少次观测后才给出冷/暖结论(避免首轮误判)。
DEFAULT_MIN_SAMPLES = 3
#: 默认命中率阈值。
DEFAULT_EFFECTIVE_RATIO = 0.2


@dataclass(frozen=True, slots=True)
class CacheObservation:
    """不可变的缓存观测聚合(逐次 usage 累加)。"""

    samples: int = 0
    input_tokens: int = 0
    cached_tokens: int = 0

    @property
    def hit_ratio(self) -> float:
        if self.input_tokens <= 0:
            return 0.0
        return min(1.0, self.cached_tokens / self.input_tokens)

    def observe(self, usage: Mapping[str, int] | None) -> "CacheObservation":
        """吸收一次 usage;缺少字段时视为 0,不制造虚假命中。"""
        if not usage:
            return self
        return CacheObservation(
            samples=self.samples + 1,
            input_tokens=self.input_tokens + max(0, int(usage.get("input_tokens", 0) or 0)),
            cached_tokens=self.cached_tokens + max(0, int(usage.get("cached_tokens", 0) or 0)),
        )

    def diagnosis(
        self,
        *,
        min_samples: int = DEFAULT_MIN_SAMPLES,
        effective_ratio: float = DEFAULT_EFFECTIVE_RATIO,
    ) -> str:
        if self.samples < min_samples or self.input_tokens <= 0:
            return CACHE_UNKNOWN
        return CACHE_EFFECTIVE if self.hit_ratio >= effective_ratio else CACHE_COLD

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "samples": self.samples,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "hit_ratio": round(self.hit_ratio, 4),
            "diagnosis": self.diagnosis(),
        }


def volatile_prefix_markers(text: str) -> tuple[str, ...]:
    """返回文本中出现的易变标记类别(去重、稳定顺序)。"""
    found: list[str] = []
    for pattern in _VOLATILE_PATTERNS:
        match = pattern.search(text)
        if match and match.group(0) not in found:
            found.append(match.group(0))
    return tuple(found)


def is_cache_friendly_prefix(text: str) -> bool:
    """前缀不含易变标记时视为可缓存。"""
    return not volatile_prefix_markers(text)
