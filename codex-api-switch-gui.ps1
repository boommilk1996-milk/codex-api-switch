# Codex API 切换 — Windows 桌面版
# 依赖：Python 3.9+（3.11+ 最佳，需要 tomllib；更早版本 pip install tomli）
#       codex-api-switch 脚本与本文件同目录，或在 PATH 中。

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

# 定位 CLI 脚本
$script = $null
foreach ($c in @((Join-Path $here "codex-api-switch"), (Join-Path $here "codex-api-switch.py"))) {
    if (Test-Path $c) {
        $script = $c
        break
    }
}

# 定位 Python 解释器
$python = $null
foreach ($cmd in @("python", "py")) {
    $found = Get-Command $cmd -ErrorAction SilentlyContinue
    if ($found) {
        $python = $found.Source
        break
    }
}

function Invoke-CLI {
    param([string[]]$CmdArgs)
    if ($script -and $python) {
        & $python $script @CmdArgs
    }
    elseif (-not $script) {
        & "codex-api-switch" @CmdArgs
    }
    else {
        Write-Host "未找到 Python。请安装 Python 3.11+（安装时勾选 Add to PATH）。" -ForegroundColor Red
    }
}

function Show-Menu {
    Clear-Host
    Write-Host "========================================"
    Write-Host "     Codex API 切换  (Windows 版)"
    Write-Host "========================================"
    Write-Host ""
    Write-Host "   1. 查看状态"
    Write-Host "   2. 切到 DeepSeek（自动同步历史对话）"
    Write-Host "   3. 切回 OpenAI（自动同步历史对话）"
    Write-Host "   4. 同步历史对话标签"
    Write-Host "   5. 保存/更新 DeepSeek API Key"
    Write-Host "   6. 查看已保存 Key"
    Write-Host "   7. 清除已保存 Key"
    Write-Host "   8. 退出"
    Write-Host ""
    Write-Host " 提示：切换前请先完全退出 Codex，否则历史对话不会同步。"
    Write-Host ""
}

$choice = ""
while ($choice -ne "8") {
    Show-Menu
    $choice = Read-Host "请选择"
    switch ($choice) {
        "1" { Invoke-CLI @("status") }
        "2" { Invoke-CLI @("deepseek") }
        "3" { Invoke-CLI @("openai") }
        "4" { Invoke-CLI @("sync") }
        "5" {
            $k = Read-Host "输入 DeepSeek API Key（以 sk- 开头）"
            if ($k) { Invoke-CLI @("key", "set", $k) }
        }
        "6" { Invoke-CLI @("key", "status") }
        "7" { Invoke-CLI @("key", "clear") }
        "8" { Write-Host "再见！" }
        default { Write-Host "无效选项，请重新输入。" -ForegroundColor Yellow }
    }
    if ($choice -ne "8") {
        Write-Host ""
        Read-Host "按回车返回菜单"
    }
}
