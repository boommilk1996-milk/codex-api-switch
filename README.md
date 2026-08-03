# codex-api-switch

一键切换 Codex 的 API 服务商（OpenAI ↔ DeepSeek Responses API），并在切换时自动同步本地对话历史标签，让旧对话在新服务商下继续全部显示。

> 非 OpenAI 官方工具。仅支持 macOS（桌面应用部分），CLI 部分跨平台。

## 为什么需要这个工具

Codex 桌面端（及 `list_threads`）会按当前 `model_provider` 过滤任务列表。切换服务商后，之前在其他服务商下创建的会话会从侧边栏"消失"——**数据并没有丢**，只是被过滤隐藏了（相关 issue：openai/codex #31625，官方尚未修复）。

本工具的 `sync` 功能把历史会话的 `model_provider` 标签统一改成当前服务商，并保持三处元数据一致：

1. `state_5.sqlite` 的 `threads.model_provider`（桌面端列表过滤依据）
2. 会话 JSONL 文件第一行 `session_meta.payload.model_provider`（Codex 重启后会用它重建数据库，只改这里才不会被覆盖）
3. `session_index.jsonl`（缺失的任务 ID 合并进去）

切换回原来的服务商时再次执行同步即可，历史会跟着搬回去。

## 功能

- `deepseek`：切到 DeepSeek Responses API（自动写 `config.toml` 与模型目录）
- `openai`：从恢复点还原 OpenAI 配置
- `sync`：把全部用户主任务的历史标签同步为当前服务商（自动备份，可回滚）
- `status` / `status --json`：查看当前配置与运行状态
- `is-running`：检测 Codex 桌面端是否在运行
- 桌面应用（JXA）：`Codex_API_切换.app.js` 编译成 macOS App，双击即可操作

## 安全设计

- **绝不读写、不打印 API Key**。DeepSeek Key 只通过 `--api-key` 参数或 `DEEPSEEK_API_KEY` 环境变量传入，写入 `config.toml` 后由你自行保管；`status` 输出仅显示掩码。
- 同步前自动备份：SQLite 在线备份 + 每个将被修改会话文件第一行的 base64 清单，存于 `~/.codex/backups/codex-api-switch/sync-<时间戳>/`，可完整回滚。
- 只修改用户主任务（`thread_source` 为 `user`/空且未归档），子任务、评审、归档会话一律不动。
- Codex 桌面端运行中**拒绝**修改历史（运行中的进程可能覆盖写入），会提示你先退出再同步。
- 每次同步只改写会话文件第一行的 provider 字段，其余字节保持不变。

## 安装

要求 Python 3.9+（需要 `tomllib`，Python 3.11+ 内置；更早版本 `pip3 install tomli`）。

```bash
# 1. 把 CLI 放进 PATH，例如：
cp codex-api-switch ~/.local/bin/
chmod +x ~/.local/bin/codex-api-switch

# 2. （可选）把模型目录放到与脚本同目录：
cp deepseek-models.json ~/.local/bin/
```

桌面应用（可选，macOS）：

```bash
osacompile -l JavaScript -o "Codex API 切换.app" Codex_API_切换.app.js
```

## 使用

```bash
# 查看当前状态
codex-api-switch status

# 先预览会同步多少条历史（只读，安全）
codex-api-switch sync --dry-run

# 完全退出 Codex 后，切到 DeepSeek（自动同步历史）
codex-api-switch deepseek --api-key 'sk-...'

# 切回 OpenAI（同样自动同步历史）
codex-api-switch openai

# 只同步历史标签，不切换配置
codex-api-switch sync
```

桌面应用使用流程：

1. 完全退出 Codex（Cmd+Q）
2. 双击 `Codex API 切换.app`
3. 点击"切到 DeepSeek"或"切回 OpenAI"
4. 应用自动完成配置切换 + 历史同步，重新打开 Codex 即可看到全部历史

## 测试

```bash
python3 test_sync.py
```

测试在临时目录模拟完整的 Codex 目录结构，覆盖：dry-run、apply、幂等性、OpenAI ↔ DeepSeek 双向切换自动同步、子任务不动、索引合并、备份清单与回滚信息。

## 已知边界

- 同步是"换标签"不是复制：会话在某服务商标签下，就由该服务商显示与续聊；切回原服务商需再次同步。
- 极早期的会话（老版本 Codex 创建）打开续聊时若遇兼容问题，可用 `~/.codex/backups/codex-api-switch/` 中的备份回滚。
