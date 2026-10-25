"""models.json:用户可编辑的自定义/覆盖配置(仿 Pi 的 models.json)。

- 用户手写,不是自动发现产物;
- 与内置目录按 id upsert 合并(见 registry.ModelRegistry)。
"""

import json
import logging
from pathlib import Path
from typing import Any

from tenon.ai.catalog.spec import ModelSpec

logger = logging.getLogger(__name__)


class ModelStore:
    """读写 models.json;文件不存在时返回空。"""

    def __init__(self, path: Path | None = None):
        """创建模型目录存储。

        ``None`` 表示不读取用户覆盖文件，仅使用内置目录；应用组合根应
        显式传入用户级 ``models.json`` 路径。
        """
        self.path = Path(path) if path is not None else None

    def load(self) -> dict[str, dict[str, list[ModelSpec]]]:
        """返回 ``{provider: {"models": [ModelSpec], ...}}``。

        文件不存在、JSON 损坏或编码无法解码时返回空并告警(不阻塞上层启动);
        每条模型记录逐字段校验类型,坏记录跳过并告警,不静默强制(H12/H13)。
        """
        if self.path is None or not self.path.exists():
            return {}
        try:
            # utf-8-sig:兼容 Windows 记事本写入的 BOM;无 BOM 时等价 utf-8(H13)
            data = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            logger.warning("读取模型目录 %s 失败(已跳过): %s", self.path, exc)
            return {}
        if not isinstance(data, dict):
            logger.warning("模型目录 %s 顶层不是对象(已跳过)", self.path)
            return {}
        result: dict[str, dict[str, list[ModelSpec]]] = {}
        for provider, conf in data.items():
            if not isinstance(conf, dict):
                logger.warning("模型目录 %s 的 provider %r 不是对象(已跳过)", self.path, provider)
                continue
            specs: list[ModelSpec] = []
            for index, m in enumerate(conf.get("models") or []):
                if not isinstance(m, dict) or not isinstance(m.get("id"), str):
                    logger.warning(
                        "模型目录 %s 的 provider %r 第 %d 条模型记录缺少字符串 id(已跳过)",
                        self.path,
                        provider,
                        index,
                    )
                    continue
                spec = _parse_record(m)
                if spec is None:
                    continue  # 类型校验失败,跳过并已告警
                specs.append(spec)
            conf["models"] = specs
            result[provider] = conf
        return result

    def write_model_override(self, provider: str, record: dict[str, Any]) -> Path:
        """按模型 id upsert 一条用户覆盖记录,返回写入的 models.json 路径。

        upsert 语义与读取一致:同 id 整体替换,新 id 追加。写入先落临时文件再
        原子替换,避免中途失败留下半截 JSON 让下次启动退回内置目录。
        """
        if self.path is None:
            raise ValueError("未指定 models.json 路径,无法写入模型覆盖")
        model_id = record.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError("模型记录缺少字符串 id")
        data = self._read_raw()
        provider_conf = data.get(provider)
        if not isinstance(provider_conf, dict):
            provider_conf = {}
            data[provider] = provider_conf
        models = provider_conf.get("models")
        if not isinstance(models, list):
            models = []
            provider_conf["models"] = models
        for index, item in enumerate(models):
            if isinstance(item, dict) and item.get("id") == model_id:
                models[index] = dict(record)
                break
        else:
            models.append(dict(record))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        temp = self.path.with_name(f"{self.path.name}.tmp")
        temp.write_text(payload, encoding="utf-8")
        temp.replace(self.path)
        return self.path

    def _read_raw(self) -> dict[str, Any]:
        """读取原始 JSON 结构;缺失或损坏时返回空对象(不阻塞写入)。"""
        path = self.path
        if path is None or not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return {}
        return raw if isinstance(raw, dict) else {}


def _parse_record(m: dict) -> ModelSpec | None:
    """把一条 models.json 记录解析为强类型 ModelSpec;类型非法返回 None 并告警。"""
    mid = m["id"]
    # camelCase(maxTokens) 与 snake_case(max_tokens) 双拼写都认(H12)
    max_tokens = m.get("maxTokens")
    if max_tokens is None:
        max_tokens = m.get("max_tokens")
    elif "max_tokens" in m and m["max_tokens"] != max_tokens:
        logger.warning("模型 %s 同时给出 maxTokens 与 max_tokens,采用 maxTokens", mid)
    # 用 type(...) is int 而非 isinstance(True 是 int 子类,会混过校验把 true 送进请求体)
    if max_tokens is not None and (type(max_tokens) is not int or max_tokens < 1):
        logger.warning(
            "模型 %s 的 maxTokens 非法(应为正整数,得到 %r),跳过",
            mid,
            max_tokens,
        )
        return None

    # contextWindow/context_window are accepted for Pi-compatible user
    # catalogs.  Keep the same strict bool/type handling as maxTokens.
    context_window = m.get("contextWindow")
    if context_window is None:
        context_window = m.get("context_window")
    elif "context_window" in m and m["context_window"] != context_window:
        logger.warning(
            "模型 %s 同时给出 contextWindow 与 context_window,采用 contextWindow",
            mid,
        )
    if context_window is not None and (type(context_window) is not int or context_window < 1):
        logger.warning(
            "模型 %s 的 contextWindow 非法(应为正整数,得到 %r),跳过",
            mid,
            context_window,
        )
        return None

    aliases = m.get("aliases", [])
    if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
        logger.warning("模型 %s 的 aliases 非法(应为 list[str],得到 %r),跳过", mid, aliases)
        return None

    reasoning, valid = _optional_bool(m, mid, "reasoning", "reasoning")
    if not valid:
        return None
    tool_calling, valid = _optional_bool(m, mid, "toolCalling", "tool_calling")
    if not valid:
        return None
    prompt_cache, valid = _optional_bool(m, mid, "promptCache", "prompt_cache")
    if not valid:
        return None

    return ModelSpec(
        id=mid,
        name=m.get("name", ""),
        reasoning=reasoning,
        max_tokens=max_tokens,
        context_window=context_window,
        tool_calling=tool_calling,
        prompt_cache=prompt_cache,
        aliases=tuple(aliases),
    )


def _optional_bool(
    record: dict[str, object],
    model_id: str,
    camel_key: str,
    snake_key: str,
) -> tuple[bool | None, bool]:
    """读取可选布尔元数据,缺失是 unknown,其它类型拒绝。"""
    has_camel = camel_key in record
    has_snake = snake_key in record
    if has_camel and has_snake and record[camel_key] != record[snake_key]:
        logger.warning(
            "模型 %s 同时给出 %s 与 %s,采用 %s",
            model_id,
            camel_key,
            snake_key,
            camel_key,
        )
    if not has_camel and not has_snake:
        return None, True
    value = record[camel_key] if has_camel else record[snake_key]
    if type(value) is not bool:
        logger.warning(
            "模型 %s 的 %s 非法(应为布尔值,得到 %r),跳过",
            model_id,
            camel_key,
            value,
        )
        return None, False
    return value, True
