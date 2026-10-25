"""按层运行 mypy 并与基线比较，把类型债务变成只能下降的棘轮门禁。

一次性让整个仓库通过严格类型检查会把无关历史债务混进功能变更，因此这里按层记
录当前错误数：任何一层错误数上升即失败；下降时提示用 ``--update`` 固化新基线。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPO_ROOT / "src" / "tenon"
BASELINE_PATH = REPO_ROOT / "docs" / "type-baseline.json"
LAYER_ROOTS = ("core", "ai", "tools", "session", "app")
SCHEMA_VERSION = 1

_ERROR_COUNT = re.compile(r"Found (\d+) error")


def run_mypy(layer: str) -> int:
    """Return the mypy error count for one layer, ignoring followed imports."""
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-m", "mypy", str(SOURCE_ROOT / layer)],
        capture_output=True,
        text=True,
        check=False,
    )
    match = _ERROR_COUNT.search(completed.stdout + completed.stderr)
    if match is not None:
        return int(match.group(1))
    if completed.returncode not in (0, 1):
        print(completed.stdout + completed.stderr)
        raise SystemExit(f"mypy 在 {layer} 层执行失败 (exit={completed.returncode})")
    return 0


def load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    layers = payload.get("layers", {})
    return {str(name): int(count) for name, count in layers.items()}


def write_baseline(counts: dict[str, int]) -> None:
    payload = {"schema_version": SCHEMA_VERSION, "layers": counts}
    BASELINE_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="类型债务棘轮检查")
    parser.add_argument(
        "--update",
        action="store_true",
        help="把当前每层错误数写为新的基线（只应在债务下降时使用）",
    )
    args = parser.parse_args()

    baseline = load_baseline()
    counts = {layer: run_mypy(layer) for layer in LAYER_ROOTS}

    if args.update:
        write_baseline(counts)
        print(f"类型基线已更新: {counts}")
        return 0

    if not baseline:
        print("缺少 docs/type-baseline.json，请先运行 scripts/type_scan.py --update")
        return 1

    regressions = [
        f"{layer}: 错误数 {counts[layer]} > 基线 {baseline.get(layer, 0)}"
        for layer in LAYER_ROOTS
        if counts[layer] > baseline.get(layer, counts[layer])
    ]
    if regressions:
        print("\n".join(regressions))
        return 1
    improvements = [
        f"{layer}: {baseline[layer]} -> {counts[layer]}"
        for layer in LAYER_ROOTS
        if layer in baseline and counts[layer] < baseline[layer]
    ]
    if improvements:
        print("类型债务已下降，可用 --update 固化基线: " + "; ".join(improvements))
    print("类型棘轮检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
