"""grep/find 的路径分支：glob 过滤、单文件目标、二进制与编码跳过、上限与加速器回退。

加速器（rg/fd）用桩替换，确保走纯 Python 回退路径，不依赖外部二进制的安装状态。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tenon.tools.atomic import find as find_mod
from tenon.tools.atomic import grep as grep_mod
from tenon.tools.atomic.find import FindTool, _glob_to_regex, find_files
from tenon.tools.atomic.grep import GrepTool, _glob_match, grep_files
from tenon.tools.shared import LocalFsOps, ToolResourceLimits

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _disable_accelerators(monkeypatch):
    """强制走 Python 回退,避免结果依赖本机是否装了 rg/fd。"""
    monkeypatch.setattr(grep_mod, "run_rg", lambda *args, **kwargs: None)
    monkeypatch.setattr(find_mod, "run_optional_search", lambda *args, **kwargs: None)


def _ops() -> LocalFsOps:
    return LocalFsOps()


# -- grep -------------------------------------------------------------------


def test_glob_match_handles_name_and_relative_path():
    """glob 同时匹配文件名与相对路径,无 rel 时只比文件名。"""
    assert _glob_match("*.py", "a.py") is True
    assert _glob_match("src/*.py", "a.py", "src/a.py") is True
    assert _glob_match("src/*.py", "a.py") is False
    assert _glob_match(None, "a.py") is True  # 未指定 glob = 全部匹配


def test_grep_rejects_empty_pattern_and_missing_path(tmp_path):
    """空 pattern 与不存在的路径都在入口拒绝。"""
    with pytest.raises(ValueError, match="pattern 不能为空"):
        grep_files(_ops(), str(tmp_path), "  ", None, None, False, False, 0, None)

    with pytest.raises(ValueError, match="路径不存在"):
        grep_files(_ops(), str(tmp_path), "needle", "missing", None, False, False, 0, None)


def test_grep_single_file_respects_glob(tmp_path):
    """目标是单个文件时仍按 glob 过滤文件名。"""
    target = tmp_path / "a.py"
    target.write_text("needle\n", encoding="utf-8")

    matched, _hit = grep_files(
        _ops(), str(tmp_path), "needle", "a.py", "*.py", False, False, 0, None
    )
    skipped, _hit2 = grep_files(
        _ops(), str(tmp_path), "needle", "a.py", "*.txt", False, False, 0, None
    )

    assert matched == ["a.py:1: needle"]
    assert skipped == []


def test_grep_skips_binary_files(tmp_path):
    """含 NUL 字节的文件按二进制跳过。"""
    (tmp_path / "bin.dat").write_bytes(b"\x00needle\x00")
    (tmp_path / "text.txt").write_bytes(b"needle\n")

    lines, _hit = grep_files(_ops(), str(tmp_path), "needle", None, None, False, False, 0, None)

    assert all("bin.dat" not in line for line in lines)
    assert any("text.txt:1: needle" in line for line in lines)


def test_grep_outputs_context_lines(tmp_path):
    """context>0 时输出上下文行,匹配行用冒号、上下文行用连字符。"""
    (tmp_path / "a.txt").write_text("before\nneedle\nafter\n", encoding="utf-8")

    lines, _hit = grep_files(_ops(), str(tmp_path), "needle", None, None, False, False, 1, None)

    assert lines == ["a.txt-1- before", "a.txt:2: needle", "a.txt-3- after"]


def test_grep_reports_limit_hit(tmp_path):
    """达到匹配上限时返回 hit=True,供工具层追加提示。"""
    (tmp_path / "a.txt").write_text("needle\nneedle\n", encoding="utf-8")

    lines, hit = grep_files(_ops(), str(tmp_path), "needle", None, None, False, False, 0, 1)

    assert len(lines) == 1
    assert hit is True


def test_grep_non_ascii_pattern_uses_string_path(tmp_path):
    """非 ASCII pattern 走文本路径,命中中文内容。"""
    (tmp_path / "cn.txt").write_text("这是中文目标\n", encoding="utf-8")
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe\x00")

    lines, _hit = grep_files(_ops(), str(tmp_path), "中文", None, None, False, False, 0, None)

    assert lines == ["cn.txt:1: 这是中文目标"]


def test_grep_tool_reports_limit_and_truncation_hints(tmp_path):
    """工具层在命中上限与输出截断时分别追加提示。"""
    (tmp_path / "a.txt").write_text("needle\n", encoding="utf-8")

    limited = GrepTool(cwd=str(tmp_path)).invoke(GrepTool.Args(pattern="needle", limit=1))

    assert "达到匹配上限 1" in str(limited)


def test_grep_tool_wraps_os_error(tmp_path):
    """文件系统访问失败 → ValueError 且带操作上下文。"""

    class _BoomOps(LocalFsOps):
        def exists(self, path):  # noqa: ANN001 - 桩
            raise OSError("device unavailable")

    with pytest.raises(ValueError, match="搜索失败: device unavailable"):
        GrepTool(cwd=str(tmp_path), ops=_BoomOps()).invoke(GrepTool.Args(pattern="x"))


# -- find -------------------------------------------------------------------


def test_glob_to_regex_supports_recursion_and_char_classes():
    """``**`` 递归匹配,字符类与未闭合方括号都有确定语义。"""
    assert _glob_to_regex("**").match("any/nested/path")
    assert _glob_to_regex("src/**/*.py").match("src/a/b/c.py")
    assert _glob_to_regex("file[!a].txt").match("fileb.txt")
    assert not _glob_to_regex("file[!a].txt").match("filea.txt")
    assert _glob_to_regex("file?.txt").match("file1.txt")
    # 未闭合的 [ 按字面量处理
    assert _glob_to_regex("a[b").match("a[b")


def test_find_rejects_empty_pattern_and_missing_or_file_path(tmp_path):
    """空 pattern、不存在路径、非目录路径都给出明确错误。"""
    with pytest.raises(ValueError, match="pattern 不能为空"):
        find_files(_ops(), str(tmp_path), "  ", None, None)

    with pytest.raises(ValueError, match="路径不存在"):
        find_files(_ops(), str(tmp_path), "*.py", "missing", None)

    file_path = tmp_path / "a.txt"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="不是目录"):
        find_files(_ops(), str(tmp_path), "*.py", "a.txt", None)


def test_find_glob_with_path_matches_relative_path(tmp_path):
    """含 / 的 pattern 对相对路径匹配,否则只匹配文件名。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")

    by_path = find_files(_ops(), str(tmp_path), "src/*.py", None, None)
    by_name = find_files(_ops(), str(tmp_path), "*.py", None, None)

    assert by_path == ["src/a.py"]
    assert by_name == ["a.py"]


def test_find_tool_reports_limit_hint(tmp_path):
    """结果数达到 limit 时追加可调大 limit 的提示。"""
    for index in range(3):
        (tmp_path / f"f{index}.py").write_text("x", encoding="utf-8")

    result = FindTool(cwd=str(tmp_path)).invoke(FindTool.Args(pattern="*.py", limit=2))

    assert "结果达到上限 2" in str(result)


def test_find_tool_wraps_os_error(tmp_path):
    """遍历失败 → ValueError 且保留原因。"""

    class _BoomOps(LocalFsOps):
        def exists(self, path):  # noqa: ANN001 - 桩
            raise OSError("disk gone")

    with pytest.raises(ValueError, match="查找失败: disk gone"):
        FindTool(cwd=str(tmp_path), ops=_BoomOps()).invoke(FindTool.Args(pattern="*.py"))


def test_try_fd_returns_none_when_truncated_or_unterminated(monkeypatch, tmp_path):
    """加速器输出不完整（截断或缺尾随 NUL）时交回 Python 回退。"""
    matcher = _glob_to_regex("*.py")
    limits = ToolResourceLimits()

    monkeypatch.setattr(
        find_mod,
        "run_optional_search",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"a.py\0", truncated=True),
    )
    assert find_mod._try_fd(tmp_path, matcher, False, None, limits) is None

    monkeypatch.setattr(
        find_mod,
        "run_optional_search",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"a.py", truncated=False),
    )
    assert find_mod._try_fd(tmp_path, matcher, False, None, limits) is None


def test_try_fd_decodes_paths_and_skips_escapes(monkeypatch, tmp_path):
    """加速器结果按相对/绝对路径归一,越界与非法编码条目被丢弃。"""
    limits = ToolResourceLimits()
    payload = b"a.py\0" + f"{tmp_path}/b.py\0".encode() + b"../outside.py\0"
    monkeypatch.setattr(
        find_mod,
        "run_optional_search",
        lambda *args, **kwargs: SimpleNamespace(stdout=payload, truncated=False),
    )

    results = find_mod._try_fd(tmp_path, _glob_to_regex("*.py"), False, None, limits)

    assert results == ["a.py", "b.py"]


def test_try_fd_respects_limit(monkeypatch, tmp_path):
    """加速器结果同样遵守 limit。"""
    monkeypatch.setattr(
        find_mod,
        "run_optional_search",
        lambda *args, **kwargs: SimpleNamespace(stdout=b"a.py\0b.py\0c.py\0", truncated=False),
    )

    results = find_mod._try_fd(tmp_path, _glob_to_regex("*.py"), False, 2, ToolResourceLimits())

    assert results == ["a.py", "b.py"]
