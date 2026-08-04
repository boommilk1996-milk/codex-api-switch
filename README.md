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

## 为什么还需要 repair（array too long 报错）

用第三方 API（如 DeepSeek）推进过的长会话，会话文件里记录的是**明文推理内容**（`reasoning` 项的 `content` 数组）。切回官方 Codex 后，续聊旧会话触发自动压缩（remote compact）时，官方 Responses API 要求 `reasoning` 项的 `content` 必须为空数组，于是报：

```text
Invalid 'input[7].content': array too long. Expected an array with maximum length 0, but got an array with length 1 instead.
```

这**不是对话丢失，也不是工具写坏文件**，只是历史消息格式与回放 API 不兼容。`repair` 会备份后把这类 `reasoning` 项的 `content` 清空（其余消息原样保留），会话即可继续推进。`openai` 切换命令会在 Codex 未运行时**自动执行修复**，无需手动干预。

## 功能

- `deepseek`：切到 DeepSeek Responses API（自动写 `config.toml` 与模型目录）
- `openai`：从恢复点还原 OpenAI 配置，并自动修复历史中的明文推理内容
- `sync`：把全部用户主任务的历史标签同步为当前服务商（自动备份，可回滚）
- `repair`：备份并清空会话文件里 `reasoning` 项的明文 `content`，修复 `array too long` 报错
- `status` / `status --json`：查看当前配置与运行状态
- `is-running`：检测 Codex 桌面端是否在运行
- 桌面应用（JXA）：`Codex_API_切换.app.js` 编译成 macOS App，双击即可操作

## 安全设计

- **绝不读写、不打印 API Key**。DeepSeek Key 只通过 `--api-key` 参数或 `DEEPSEEK_API_KEY` 环境变量传入，写入 `config.toml` 后由你自行保管；`status` 输出仅显示掩码。
- 同步前自动备份：SQLite 在线备份 + 每个将被修改会话文件第一行的 base64 清单，存于 `~/.codex/backups/codex-api-switch/sync-<时间戳>/`，可完整回滚。
- 修复前自动备份：每个被修复的会话文件原样复制 + SHA-256 清单，存于 `~/.codex/backups/codex-api-switch/repair-<时间戳>/`，可完整回滚。
- 只修改用户主任务（`thread_source` 为 `user`/空且未归档），子任务、评审、归档会话一律不动。
- Codex 桌面端运行中**拒绝**修改历史（运行中的进程可能覆盖写入），会提示你先退出再同步/修复。
- 每次同步只改写会话文件第一行的 provider 字段，其余字节保持不变。

## 安装

要求 Python 3.9+（需要 `tomllib`，Python 3.11+ 内置；更早版本 `pip3 install tomli`）。

### 方式一：一键安装（推荐）

下载仓库后，在仓库根目录执行：

```bash
bash install.sh              # 安装 CLI 到 ~/.local/bin
bash install.sh --app        # 顺便编译 macOS 桌面应用
bash install.sh --prefix DIR # 安装到自定义目录
```

脚本会自动检查 Python 版本、安装缺失的 `tomli`、把 `codex-api-switch` 放进 PATH（并提示如果不在），可选编译桌面应用。

### 方式二：手动安装

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

### Windows

1. 安装 Python 3.11+（安装时勾选 **Add to PATH**）
2. 双击 `Codex API 切换.cmd` 打开菜单（或右键以 PowerShell 运行 `codex-api-switch-gui.ps1`）
3. 按菜单操作：查看状态 / 切换服务商 / 同步历史 / 管理 Key

CLI 在 Windows 上同样可用（`codex-api-switch status / deepseek / openai / sync / key / repair`），进程检测会自动使用 `tasklist` 判断 Codex 是否运行。

### 使用前的准备

1. 本机已安装 Codex（工具操作的是 `~/.codex/` 下的配置与会话）。
2. 准备一个 DeepSeek API Key：到 DeepSeek 开放平台注册并创建 `sk-` 开头的 Key。**工具不包含任何现成 Key**。

## 使用

```bash
# 查看当前状态
codex-api-switch status

# 先预览会同步多少条历史（只读，安全）
codex-api-switch sync --dry-run

# 保存 DeepSeek API Key（只需一次，之后切换不再询问）
codex-api-switch key set 'sk-...'
codex-api-switch key status        # 查看是否已保存（只显示掩码）
codex-api-switch key clear         # 忘记已保存的 Key

# 完全退出 Codex 后，切到 DeepSeek（自动同步历史，Key 自动读取）
codex-api-switch deepseek

# 切回 OpenAI（自动同步历史 + 自动修复 reasoning 历史，防止 array too long）
codex-api-switch openai

# 只同步历史标签，不切换配置
codex-api-switch sync

# 排查 / 修复 array too long：
codex-api-switch repair --all --dry-run   # 先只看哪些会话需要修复
codex-api-switch repair <会话id>           # 修复指定会话（自动备份）
codex-api-switch repair --all              # 修复全部受影响会话（自动备份）
```

桌面应用使用流程：

1. 完全退出 Codex（Cmd+Q）
2. 双击 `Codex API 切换.app`
3. 首次切换时按提示填写一次 DeepSeek API Key（之后永久保存，不会再问）
4. 点击"切到 DeepSeek"或"切回 OpenAI"
5. 应用自动完成配置切换 + 历史同步，重新打开 Codex 即可看到全部历史

DeepSeek API Key 保存在 `~/.codex/backups/codex-api-switch/deepseek-key`（权限 600，仅当前用户可读），切回 OpenAI 也不会丢失；需要更换时用 `codex-api-switch key set 'sk-...'` 覆盖即可。

## 测试

```bash
python3 test_sync.py
```

测试在临时目录模拟完整的 Codex 目录结构，覆盖：dry-run、apply、幂等性、OpenAI ↔ DeepSeek 双向切换自动同步、子任务不动、索引合并、备份清单与回滚信息、`repair` 单会话/全部/幂等/运行中拒绝/切换自动修复。

## 已知边界

- 同步是"换标签"不是复制：会话在某服务商标签下，就由该服务商显示与续聊；切回原服务商需再次同步。
- `repair` 会清空旧会话里的明文推理内容，修复后该会话在官方 API 下可正常回放；DeepSeek 侧的续聊不依赖这些明文内容（推理内容由模型重新生成）。
- 极早期的会话（老版本 Codex 创建）打开续聊时若遇兼容问题，可用 `~/.codex/backups/codex-api-switch/` 中的备份回滚。
