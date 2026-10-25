# 贡献指南

感谢参与 `tenon`。提交代码前请先阅读 [AGENTS.md](AGENTS.md) 中的分层约束、编码规范与完成标准；本文件只列出最短协作路径。

## 开发环境

```bash
git clone https://github.com/qsxcde/tenon.git
cd tenon
uv sync --group dev
```

测试必须离线、可重复，不依赖真实凭据、真实 Provider 或真实网络。外部边界使用 `tmp_path`、`monkeypatch` 与 `FakeClient`。

## 提交前检查

```bash
uv run pytest -m "unit or contract" -q --strict-markers
uv run ruff check src tests evals scripts
uv run ruff format --check src tests evals scripts
uv run python scripts/type_scan.py
uv run python scripts/scale_scan.py
openspec validate --specs
```

行为变更还应运行相关集成测试，必要时运行 `uv run pytest -q`。类型棘轮只允许下降，规模门禁要求生产层单文件 ≤300 行、单函数 ≤80 行。

## 变更要求

- 新增或修复行为必须补充回归测试；新增测试使用正确的 pytest marker。
- 涉及公共接口、持久化格式或架构边界时，先更新 `openspec/` 变更提案与主规格。
- 保持改动范围最小，不混入无关重构、格式化或重命名。
- 不提交密钥、用户会话数据、构建产物或本地配置。

## 提交信息

使用简短祈使句与仓库前缀：`feat:`、`fix:`、`docs:`、`test:`、`ci:`、`chore:`。一次提交只做一件主要事情。

## Pull Request

PR 需说明行为变化、影响范围、风险、验证命令与未覆盖部分。涉及 TUI 的变更请附截图或终端录屏。合并前需通过 CI 的 Ruff、快速测试、覆盖率、三平台离线测试与 package-smoke。

## 安全问题

不要在公开 Issue 中披露可利用细节或真实凭据。请先通过仓库维护者私下联系，并在修复发布后再公开讨论。

## 许可证

提交贡献即表示同意以 [MIT License](LICENSE) 授权。
