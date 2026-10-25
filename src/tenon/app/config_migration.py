"""旧配置目录的一次性迁移。

独立成模块是为了让 ``app/config.py`` 维持在规模门禁以内;这里不 import
``config``,目录常量由调用方注入,避免循环依赖。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path


def migrate_legacy_config(current: Path, legacy: Path) -> Path | None:
    """把 ``legacy`` 整体迁移到 ``current``。

    仅在 ``current`` 不存在且 ``legacy`` 存在时动作;两者并存时保持现状,
    避免覆盖用户已经在新目录下写好的配置;迁移失败只告警,不阻塞启动。
    """
    if current.exists() or not legacy.exists():
        return None
    try:
        shutil.move(str(legacy), str(current))
    except OSError as exc:
        logging.warning("旧配置目录迁移失败 %s: %s", legacy, exc)
        return None
    logging.info("配置目录已迁移: %s -> %s", legacy, current)
    return current
