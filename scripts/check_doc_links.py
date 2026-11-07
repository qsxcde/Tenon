"""检查仓库内 Markdown 文档的相对链接是否失效。

只检查 ``README.md`` 与 ``docs/`` 下的相对链接，跳过 http(s)/mailto 与纯锚点。
输出失效链接并以非零状态退出，供本地和 CI 使用。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")


def is_external(target: str) -> bool:
    return not target or target.startswith(_SKIP_PREFIXES)


def broken_links(document: Path) -> list[str]:
    """Return every relative link in ``document`` that points to a missing path."""
    text = document.read_text(encoding="utf-8")
    broken: list[str] = []
    for match in _LINK.finditer(text):
        target = match.group(1).strip()
        if is_external(target):
            continue
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue
        resolved = (document.parent / path_part).resolve()
        if not resolved.exists():
            broken.append(f"{document.relative_to(ROOT).as_posix()}: {target}")
    return broken


def documents() -> list[Path]:
    """Collect the markdown files that participate in the link gate."""
    files = [ROOT / "README.md"]
    files.extend(sorted((ROOT / "docs").rglob("*.md")))
    return [path for path in files if path.is_file()]


def main() -> int:
    failures: list[str] = []
    for document in documents():
        failures.extend(broken_links(document))
    if failures:
        for failure in failures:
            print(f"失效链接 {failure}", file=sys.stderr)
        return 1
    print(f"文档链接检查通过（{len(documents())} 个文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
