// Codex API 切换 — JXA Applet (v2: history sync)
// Calls codex-api-switch Python script, checks Codex is closed before
// switching so conversation history labels can be synced automatically.

const app = Application.currentApplication();
app.includeStandardAdditions = true;

// ── helpers ────────────────────────────────────────────────────────────────

function sh(cmd) {
    // Locate the switcher: $CODEX_API_SWITCH override -> PATH -> common spots.
    // doShellScript in an applet runs with a minimal PATH, so we probe
    // absolute locations explicitly before falling back to a bare name.
    const override = app
        .doShellScript('printf "%s" "$CODEX_API_SWITCH"')
        .trim();
    const home = app.doShellScript('printf "%s" "$HOME"').trim();
    const candidates = override
        ? [override]
        : [
              "/usr/local/bin/codex-api-switch",
              "/opt/homebrew/bin/codex-api-switch",
              `${home}/.local/bin/codex-api-switch`,
              "codex-api-switch",
          ];
    let found = "";
    for (const candidate of candidates) {
        const q = "'" + String(candidate).replace(/'/g, "'\\''") + "'";
        const ok = app
            .doShellScript(`command -v ${q} >/dev/null 2>&1 && echo yes`)
            .trim();
        if (ok === "yes") {
            found = candidate;
            break;
        }
    }
    const q = "'" + found.replace(/'/g, "'\\''") + "'";
    // Run switcher command, capturing stdout + stderr.
    // Redirect stderr to stdout so errors are visible in the result.
    return app.doShellScript(`${q} ${cmd} 2>&1`);
}

function shJSON(cmd) {
    try {
        return JSON.parse(sh(cmd));
    } catch (_) {
        return null;
    }
}

function status() { return shJSON("status --json"); }

function isRunning() {
    try {
        return sh("is-running").trim() === "running";
    } catch (_) {
        return false;
    }
}

function emojiProvider(s) {
    if (!s || s === "openai") return "⚡ OpenAI";
    return "🧠 DeepSeek";
}

function maskKey(key) {
    if (!key || key.length <= 10) return key || "(未配置)";
    return key.slice(0, 5) + "***" + key.slice(-4);
}

// ── dialogs ────────────────────────────────────────────────────────────────

function showError(title, msg) {
    app.displayAlert(title, {
        message: String(msg).slice(0, 500),
        as: "critical",
        buttons: ["好"],
        defaultButton: "好",
    });
}

function showInfo(title, msg) {
    app.displayDialog(String(msg).slice(0, 1600), {
        withTitle: title,
        buttons: ["好"],
        defaultButton: "好",
    });
}

// Ask the user to quit Codex first when it is still running.
// Returns true when it is safe to continue switching.
function confirmCodexQuit() {
    if (!isRunning()) return true;
    let choice;
    try {
        choice = app.displayDialog(
            "Codex 正在运行，此时切换不会同步历史对话。\n\n" +
            "请先完全退出 Codex（Cmd+Q），然后重新双击本应用点击切换，将自动把全部历史对话搬到新服务商。\n\n" +
            "如果选择「仅切换配置」，历史对话保持原标签，之后可手动运行 codex-api-switch sync 同步。",
            {
                withTitle: "请先退出 Codex",
                buttons: ["我先退出 Codex", "仅切换配置", "取消"],
                defaultButton: "我先退出 Codex",
                cancelButton: "取消",
            }
        ).buttonReturned;
    } catch (_) {
        return false; // cancelled
    }
    if (choice === "我先退出 Codex") {
        showInfo("已了解", "退出 Codex 后，重新双击本应用并点击切换即可，历史对话会自动全部显示。");
        return false;
    }
    return choice === "仅切换配置";
}

// ── main ───────────────────────────────────────────────────────────────────

function main() {
    // 1. Get current state
    let st;
    try {
        st = status();
    } catch (e) {
        showError("获取状态失败", `无法读取 Codex 配置。\n\n${e.message || e}`);
        return;
    }

    if (!st) {
        showError("获取状态失败", "无法解析 Codex 配置状态。请检查 config.toml 是否正常。");
        return;
    }

    // 2. Build status summary
    const providerIcon = emojiProvider(st.provider);
    const providerLabel = st.is_deepseek ? "DeepSeek" : "OpenAI";
    const modelName = st.model || "(未设置)";
    const deepseekInfo = st.deepseek_configured
        ? `DeepSeek: 已配置 (${st.deepseek_base_url || ""})`
        : "DeepSeek: 未配置";
    const keyInfo = st.deepseek_key_available
        ? "DeepSeek Key: 已保存（切换时无需再填）"
        : "DeepSeek Key: 未保存（首次切换时填写一次即可）";
    const restoreInfo = st.restore_available ? "恢复点: 可用" : "恢复点: 无";
    const runningInfo = st.codex_running ? "Codex: 运行中（切换前请先退出）" : "Codex: 未运行（可安全切换）";

    const statusLines = [
        `当前: ${providerLabel}  ·  ${modelName}`,
        deepseekInfo,
        keyInfo,
        restoreInfo,
        runningInfo,
        "",
        "切换后需重启 Codex 桌面端或新开 CLI 会话。",
    ].join("\n");

    // 3. Choose action — buttons depend on current state
    let buttons;
    let defaultButton;

    if (st.is_deepseek) {
        buttons = ["切回 OpenAI", "查看详情", "取消"];
        defaultButton = "切回 OpenAI";
    } else {
        buttons = ["切到 DeepSeek", "查看详情", "取消"];
        defaultButton = "切到 DeepSeek";
    }

    let choice;
    try {
        choice = app.displayDialog(statusLines, {
            withTitle: "Codex API 切换",
            buttons: buttons,
            defaultButton: defaultButton,
            cancelButton: "取消",
        }).buttonReturned;
    } catch (_) {
        // User cancelled
        return;
    }

    // 4. Details
    if (choice === "查看详情") {
        let detail;
        try {
            detail = sh("status");
        } catch (e) {
            showError("获取详情失败", e.message || e);
            return;
        }
        showInfo("Codex API 详情", detail);
        return;
    }

    // 5. Switching — require Codex to be quit so history sync can run
    const switchingToDeepseek = choice === "切到 DeepSeek";
    if (!confirmCodexQuit()) return;

    if (switchingToDeepseek) {
        // If not configured, ask for API key first
        let apiKeyArg = "";
        if (!st.deepseek_key_available) {
            let keyInput;
            try {
                keyInput = app.displayDialog(
                    "首次切换需要 DeepSeek API Key。\nKey 只会保存一次，之后切换不再需要填写。\n\n请输入你的 DeepSeek API Key（以 sk- 开头）：",
                    {
                        withTitle: "配置 DeepSeek API Key",
                        defaultAnswer: "",
                        buttons: ["确认切换", "取消"],
                        defaultButton: "确认切换",
                        cancelButton: "取消",
                        hiddenAnswer: true,
                    }
                );
            } catch (_) {
                return; // user cancelled
            }
            const key = (keyInput.textReturned || "").trim();
            if (!key) {
                showError("未输入 API Key", "需要提供 DeepSeek API Key 才能切换。");
                return;
            }
            if (!key.startsWith("sk-")) {
                showError("Key 格式错误", "DeepSeek API Key 应以 sk- 开头。未做任何更改。");
                return;
            }
            apiKeyArg = ` --api-key '${key.replace(/'/g, "'\\''")}'`;
        }

        let result;
        try {
            result = sh(`deepseek${apiKeyArg}`);
        } catch (e) {
            showError("切换失败", `切到 DeepSeek 时出错:\n\n${e.message || e}`);
            return;
        }
        // Check if it actually switched by re-reading status
        try { st = status(); } catch (_) { st = null; }
        const newModel = st ? st.model : "deepseek-v4-flash";
        showInfo("已切到 DeepSeek",
            `${result}\n\n当前模型: ${newModel}\n请重启 Codex 后使用。`);
        return;
    }

    if (choice === "切回 OpenAI") {
        let result;
        try {
            result = sh("openai");
        } catch (e) {
            showError("切换失败", `切回 OpenAI 时出错:\n\n${e.message || e}`);
            return;
        }
        try { st = status(); } catch (_) { st = null; }
        const newModel = st ? st.model : "gpt-5.5";
        showInfo("已切回 OpenAI",
            `${result}\n\n当前模型: ${newModel}\n请重启 Codex 后使用。`);
        return;
    }
}

// ── entry ──────────────────────────────────────────────────────────────────

try {
    main();
} catch (e) {
    showError("Codex API 切换出错", e.message || String(e));
}
