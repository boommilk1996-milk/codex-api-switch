#!/usr/bin/env python3
"""Integration test for codex-api-switch history sync on a simulated home."""

from __future__ import annotations

import json
import base64
import argparse
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
from unittest import mock
from pathlib import Path


SWITCHER = Path(__file__).parent / "codex-api-switch"


def make_rollout(path: Path, thread_id: str, provider: str) -> None:
    first = json.dumps(
        {
            "timestamp": "2026-08-03T00:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "session_id": thread_id,
                "id": thread_id,
                "timestamp": "2026-08-03T00:00:00.000Z",
                "cwd": "/fake/project",
                "originator": "Codex Desktop",
                "cli_version": "0.146.0",
                "source": "vscode",
                "thread_source": "user",
                "model_provider": provider,
            },
        },
        ensure_ascii=False,
    )
    body = (
        json.dumps({"type": "user_message", "payload": {"content": "hello"}})
        + "\n"
        + json.dumps({"type": "agent_message", "payload": {"content": "hi"}})
        + "\n"
    )
    path.write_text(first + "\n" + body, encoding="utf-8")


def add_reasoning_history(path: Path, count: int = 3) -> None:
    """Append response_item lines with plaintext reasoning content (DeepSeek-era shape)."""
    lines = []
    for i in range(count):
        lines.append(
            json.dumps(
                {
                    "timestamp": "2026-08-03T00:00:0X.000Z",
                    "type": "response_item",
                    "payload": {
                        "type": "reasoning",
                        "id": f"reasoning-{i}",
                        "summary": [],
                        "content": [{"type": "reasoning_text", "text": f"thinking {i}"}],
                        "encrypted_content": None,
                    },
                },
                ensure_ascii=False,
            )
        )
    lines.append(
        json.dumps(
            {
                "timestamp": "2026-08-03T00:00:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "reasoning",
                    "id": "reasoning-empty",
                    "summary": [],
                    "content": [],
                    "encrypted_content": None,
                },
            },
            ensure_ascii=False,
        )
    )
    lines.append(
        json.dumps(
            {
                "timestamp": "2026-08-03T00:00:00.000Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "id": "call-1",
                    "name": "exec_command",
                    "arguments": "{}",
                    "call_id": "call_00_x",
                },
            },
            ensure_ascii=False,
        )
    )
    with path.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


def setup_home(home: Path) -> None:
    (home / "ipc").mkdir(parents=True)
    (home / "backups" / "codex-api-switch").mkdir(parents=True)
    (home / "config.toml").write_text('model_provider = "deepseek"\nmodel = "deepseek-v4-flash"\n')

    db = home / "state_5.sqlite"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE threads (
            id TEXT PRIMARY KEY,
            rollout_path TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            source TEXT NOT NULL,
            model_provider TEXT NOT NULL,
            cwd TEXT NOT NULL,
            title TEXT NOT NULL,
            sandbox_policy TEXT NOT NULL,
            approval_mode TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            has_user_event INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0,
            archived_at INTEGER,
            git_sha TEXT,
            git_branch TEXT,
            git_origin_url TEXT,
            cli_version TEXT NOT NULL DEFAULT '',
            first_user_message TEXT NOT NULL DEFAULT '',
            agent_nickname TEXT,
            agent_role TEXT,
            memory_mode TEXT NOT NULL DEFAULT 'enabled',
            model TEXT,
            reasoning_effort TEXT,
            agent_path TEXT,
            created_at_ms INTEGER,
            updated_at_ms INTEGER,
            thread_source TEXT,
            preview TEXT NOT NULL DEFAULT '',
            recency_at INTEGER NOT NULL DEFAULT 0,
            recency_at_ms INTEGER NOT NULL DEFAULT 0,
            history_mode TEXT NOT NULL DEFAULT 'legacy',
            name TEXT,
            is_pinned INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    tasks = [
        ("task-aaa", "rollout-a.jsonl", "openai", "Alpha project"),
        ("task-bbb", "rollout-b.jsonl", "openai", "Beta project"),
        ("task-ccc", "rollout-c.jsonl", "deepseek", "Gamma project"),
        ("task-ddd", "rollout-d.jsonl", "openai", "Delta subagent", "subagent"),
    ]
    now = 1780000000000
    for task in tasks:
        tid, rname, provider, title = task[0], task[1], task[2], task[3]
        ts = task[4] if len(task) > 4 else "user"
        conn.execute(
            "INSERT INTO threads (id, rollout_path, created_at, updated_at, source,"
            " model_provider, cwd, title, sandbox_policy, approval_mode, thread_source)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (tid, str(home / rname), now, now, "vscode", provider,
             "/fake/project", title, "workspace-write", "default", ts),
        )
        make_rollout(home / rname, tid, provider)
    conn.commit()
    conn.close()

    (home / "session_index.jsonl").write_text(
        json.dumps({"id": "task-ccc", "thread_name": "Gamma project"}) + "\n",
        encoding="utf-8",
    )


def run(*args: str, home: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["CODEX_SWITCH_HOME"] = str(home)
    return subprocess.run(
        [sys.executable, str(SWITCHER), *args],
        capture_output=True, text=True, env=env,
    )


def check(cond: bool, label: str) -> None:
    if not cond:
        print(f"FAIL: {label}")
        raise SystemExit(1)
    print(f"PASS: {label}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="codex-switch-test-") as tmp:
        home = Path(tmp)
        setup_home(home)

        # 1. dry-run: only openai user tasks should be listed
        r = run("sync", "--dry-run", home=home)
        check(r.returncode == 0, f"dry-run exit 0 (got {r.returncode})")
        check("Tasks to relabel: 2" in r.stdout, "dry-run reports 2 tasks")
        check("Dry run: no files were changed." in r.stdout, "dry-run changes nothing")
        first_after_dry = (home / "rollout-a.jsonl").read_text(encoding="utf-8")
        check('"model_provider": "openai"' in first_after_dry, "dry-run left rollout untouched")

        # 2. apply
        r = run("sync", "--yes", home=home)
        check(r.returncode == 0, f"apply exit 0 (got {r.returncode}, stderr={r.stderr})")
        check("Updated: 2 conversations" in r.stdout, "apply reports 2 updated")
        check("session_index.jsonl: merged 2 missing id(s)" in r.stdout, "index merged 2 ids")
        check("Backup:" in r.stdout, "backup dir reported")

        # 3. rollout first lines relabeled, body intact
        for rname, expected in (("rollout-a.jsonl", "deepseek"), ("rollout-b.jsonl", "deepseek")):
            text = (home / rname).read_text(encoding="utf-8")
            lines = text.split("\n")
            check(
                f'"model_provider": "{expected}"' in lines[0],
                f"{rname} first line relabeled to {expected}",
            )
            check('"type": "user_message"' in lines[1], f"{rname} body intact")
        c_text = (home / "rollout-c.jsonl").read_text(encoding="utf-8")
        check('"model_provider": "deepseek"' in c_text.split("\n")[0], "deepseek rollout untouched")

        # 4. sqlite updated
        conn = sqlite3.connect(home / "state_5.sqlite")
        rows = dict(conn.execute("SELECT id, model_provider FROM threads").fetchall())
        conn.close()
        check(rows["task-aaa"] == "deepseek" and rows["task-bbb"] == "deepseek", "sqlite rows updated")
        check(rows["task-ccc"] == "deepseek", "deepseek row unchanged")
        check(rows["task-ddd"] == "openai", "subagent row untouched")

        # 5. index contains both ids now
        index = (home / "session_index.jsonl").read_text(encoding="utf-8")
        check("task-aaa" in index and "task-bbb" in index, "index merged new ids")
        check("task-ccc" in index, "existing index entry preserved")

        # 6. backup manifest exists and can restore the original first lines
        backup_dirs = sorted(
            (home / "backups" / "codex-api-switch").glob("sync-*"),
            key=lambda p: p.name,
        )
        check(len(backup_dirs) == 1, "one sync backup snapshot")
        manifest = json.loads((backup_dirs[0] / "manifest.json").read_text(encoding="utf-8"))
        check(set(manifest) == {"task-aaa", "task-bbb"}, "manifest covers updated tasks")
        orig = json.loads(base64.b64decode(manifest["task-aaa"]["first_line_b64"]).decode("utf-8"))
        check(orig["payload"]["model_provider"] == "openai", "manifest stored original provider")

        # 7. apply again -> no-op
        r = run("sync", "--yes", home=home)
        check("Tasks to relabel: 0" in r.stdout, "second sync is a no-op")

        # 8. switch command auto-syncs history (openai -> deepseek)
        (home / "config.toml").write_text('model_provider = "openai"\nmodel = "gpt-5.5"\n')
        conn = sqlite3.connect(home / "state_5.sqlite")
        conn.execute(
            "UPDATE threads SET model_provider='openai' "
            "WHERE id IN ('task-aaa','task-bbb','task-ccc')"
        )
        conn.commit()
        conn.close()
        for rname in ("rollout-a.jsonl", "rollout-b.jsonl", "rollout-c.jsonl"):
            p = home / rname
            first, _, rest = p.read_text(encoding="utf-8").partition("\n")
            first = first.replace('"model_provider": "deepseek"', '"model_provider": "openai"')
            p.write_text(first + "\n" + rest, encoding="utf-8")
        env = dict(os.environ)
        env["CODEX_SWITCH_HOME"] = str(home)
        env["DEEPSEEK_API_KEY"] = "sk-test-1234567890"
        r = subprocess.run(
            [sys.executable, str(SWITCHER), "deepseek"],
            capture_output=True, text=True, env=env,
        )
        check(r.returncode == 0, f"deepseek switch exit 0 (got {r.returncode}, {r.stderr})")
        check("Switched to DeepSeek" in r.stdout, "deepseek switch reported")
        check("History synced: 3 conversation(s)" in r.stdout, "deepseek switch auto-synced 3")
        cfg = (home / "config.toml").read_text(encoding="utf-8")
        check('model_provider = "deepseek"' in cfg, "config switched to deepseek")
        conn = sqlite3.connect(home / "state_5.sqlite")
        providers = set(
            row[0]
            for row in conn.execute(
                "SELECT model_provider FROM threads WHERE thread_source='user'"
            ).fetchall()
        )
        conn.close()
        check(providers == {"deepseek"}, "all user tasks relabeled to deepseek")

        # 9. switch back to openai also auto-syncs
        r = subprocess.run(
            [sys.executable, str(SWITCHER), "openai"],
            capture_output=True, text=True, env=env,
        )
        check(r.returncode == 0, f"openai switch exit 0 (got {r.returncode}, {r.stderr})")
        check("Restored to OpenAI config" in r.stdout, "openai switch reported")
        check("History synced: 3 conversation(s)" in r.stdout, "openai switch auto-synced 3")
        cfg = (home / "config.toml").read_text(encoding="utf-8")
        check('model_provider = "openai"' in cfg, "config restored to openai")
        conn = sqlite3.connect(home / "state_5.sqlite")
        providers = set(
            row[0]
            for row in conn.execute(
                "SELECT model_provider FROM threads WHERE thread_source='user'"
            ).fetchall()
        )
        conn.close()
        check(providers == {"openai"}, "all user tasks relabeled back to openai")

        # 10. key persistence: set once, switch without --api-key or env
        with tempfile.TemporaryDirectory(prefix="codex-switch-key-test-") as tmp2:
            home2 = Path(tmp2)
            setup_home(home2)
            # simulate an OpenAI-only config (no deepseek token anywhere)
            (home2 / "config.toml").write_text('model_provider = "openai"\nmodel = "gpt-5.5"\n')
            env2 = dict(os.environ)
            env2["CODEX_SWITCH_HOME"] = str(home2)
            env2.pop("DEEPSEEK_API_KEY", None)

            # no key anywhere -> switch must fail with a clear message
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "deepseek"],
                capture_output=True, text=True, env=env2,
            )
            check(r.returncode == 2, f"no key -> deepseek fails (got {r.returncode})")
            check("No DeepSeek API key found" in r.stderr, "no-key error message")

            # save the key once
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "key", "set", "sk-saved-1234567890"],
                capture_output=True, text=True, env=env2,
            )
            check(r.returncode == 0, "key set exits 0")
            key_file = home2 / "backups" / "codex-api-switch" / "deepseek-key"
            check(key_file.exists(), "key file created")
            check((key_file.stat().st_mode & 0o777) == 0o600, "key file mode 600")

            # switch to deepseek now works from the saved key, no prompt needed
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "deepseek"],
                capture_output=True, text=True, env=env2,
            )
            check(r.returncode == 0, f"saved-key deepseek switch exit 0 (got {r.returncode})")
            check("Switched to DeepSeek" in r.stdout, "saved-key switch succeeded")
            check("key saved for future switches" in r.stdout, "switch reports key saved")

            # switch back to openai: key must survive (copied from config)
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "openai"],
                capture_output=True, text=True, env=env2,
            )
            check(r.returncode == 0, "openai switch exit 0")
            check(key_file.exists(), "key file survives openai switch")

            # switch to deepseek again: still no prompt
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "deepseek"],
                capture_output=True, text=True, env=env2,
            )
            check(r.returncode == 0, "second deepseek switch exit 0 without key")

            # key status shows a masked value; clear removes it
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "key", "status"],
                capture_output=True, text=True, env=env2,
            )
            check("sk-sa***7890" in r.stdout, "key status masks value")
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "key", "clear"],
                capture_output=True, text=True, env=env2,
            )
            check(r.returncode == 0, "key clear exit 0")
            check(not key_file.exists(), "key file removed after clear")

            # status --json reports key availability (config back to openai = no token anywhere)
            (home2 / "config.toml").write_text('model_provider = "openai"\nmodel = "gpt-5.5"\n')
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "status", "--json"],
                capture_output=True, text=True, env=env2,
            )
            st = json.loads(r.stdout)
            check(st["deepseek_key_available"] is False, "json reports no saved key after clear")

        # 11. Windows process detection (tasklist branch)
        import types

        mod = types.ModuleType("codex_api_switch_mod")
        mod.__file__ = str(SWITCHER)
        with open(SWITCHER, encoding="utf-8") as fh:
            exec(compile(fh.read(), str(SWITCHER), "exec"), mod.__dict__)

        with mock.patch.object(platform, "system", return_value="Windows"):
            with mock.patch.object(
                subprocess, "run", side_effect=FileNotFoundError
            ):
                check(
                    mod.is_codex_running() is False,
                    "windows: no tasklist -> not running",
                )
            fake = subprocess.CompletedProcess([], 0, stdout="ChatGPT.exe", stderr="")
            with mock.patch.object(subprocess, "run", return_value=fake):
                check(
                    mod.is_codex_running() is True,
                    "windows: ChatGPT.exe detected as running",
                )

        # 12. openai restore self-heals a restore point missing model_provider
        with tempfile.TemporaryDirectory(prefix="codex-switch-heal-test-") as tmp3:
            home3 = Path(tmp3)
            setup_home(home3)
            bak = home3 / "backups" / "codex-api-switch"
            bak.mkdir(parents=True, exist_ok=True)
            (bak / "openai-last.toml").write_text(
                'model = "gpt-5.5"\nmodel_reasoning_effort = "medium"\n'
            )
            r = run("openai", home=home3)
            check(
                r.returncode == 0,
                f"openai switch with broken restore point exit 0 (got {r.returncode})",
            )
            check(
                "missing model_provider; repaired" in r.stdout,
                "self-heal message printed",
            )
            cfg = (home3 / "config.toml").read_text(encoding="utf-8")
            check('model_provider = "openai"' in cfg, "config repaired with model_provider")
            r = run("status", "--json", home=home3)
            st = json.loads(r.stdout)
            check(st["provider"] == "openai", "status reports openai after repair")

        # 13. provider switch clears the stale Codex model cache
        with tempfile.TemporaryDirectory(prefix="codex-switch-cache-test-") as tmp4:
            home4 = Path(tmp4)
            setup_home(home4)
            (home4 / "config.toml").write_text('model_provider = "openai"\nmodel = "gpt-5.5"\n')
            cache = home4 / "models_cache.json"
            cache.write_text('{"models":[{"slug":"gpt-5.6-sol"}]}\n', encoding="utf-8")
            env4 = dict(os.environ)
            env4["CODEX_SWITCH_HOME"] = str(home4)
            env4["DEEPSEEK_API_KEY"] = "sk-test-1234567890"
            r = subprocess.run(
                [sys.executable, str(SWITCHER), "deepseek"],
                capture_output=True, text=True, env=env4,
            )
            check(
                r.returncode == 0,
                f"deepseek switch with stale cache exit 0 (got {r.returncode})",
            )
            check(
                "Removed stale Codex model cache" in r.stdout,
                "cache removal message printed",
            )
            check(not cache.exists(), "stale cache file removed")
            cache_baks = list(
                (home4 / "backups" / "codex-api-switch").glob(
                    "models_cache-removed-*.json"
                )
            )
            check(len(cache_baks) == 1, "cache backed up before removal")

        # 14. repair subcommand empties reasoning content (array_above_max_length fix)
        with tempfile.TemporaryDirectory(prefix="codex-switch-repair-test-") as tmp5:
            home5 = Path(tmp5)
            setup_home(home5)
            a_path = home5 / "rollout-a.jsonl"
            c_path = home5 / "rollout-c.jsonl"
            add_reasoning_history(a_path, 3)
            add_reasoning_history(c_path, 1)

            # dry-run: reports both sessions, changes nothing
            r = run("repair", "--all", "--dry-run", home=home5)
            check(r.returncode == 0, f"repair --all --dry-run exit 0 (got {r.returncode})")
            check("Sessions to repair: 2" in r.stdout, "dry-run finds 2 sessions")
            check("Dry run: no files were changed." in r.stdout, "repair dry-run changes nothing")
            after_dry = a_path.read_text(encoding="utf-8")
            check('"text": "thinking 0"' in after_dry, "dry-run left reasoning content intact")

            # repair one session by id
            r = run("repair", "task-aaa", "-y", home=home5)
            check(r.returncode == 0, f"repair by id exit 0 (got {r.returncode}, {r.stderr})")
            check("Repaired: 3 reasoning item(s) in 1 session(s)" in r.stdout, "repair reports 3 items")
            check("Backup:" in r.stdout, "repair reports backup")
            a_text = a_path.read_text(encoding="utf-8")
            check('"text": "thinking 0"' not in a_text, "reasoning text removed")
            check('"content":[]' in a_text, "reasoning content emptied")
            check('"type": "function_call"' in a_text, "function_call item untouched")
            check('"type": "user_message"' in a_text, "message items untouched")
            check('"id": "reasoning-empty"' in a_text, "already-empty reasoning kept")
            check(
                '"model_provider": "openai"' in a_text.split("\n")[0],
                "session_meta first line untouched by repair",
            )

            # backup snapshot exists with manifest
            repair_baks = sorted(
                (home5 / "backups" / "codex-api-switch").glob("repair-*"),
                key=lambda p: p.name,
            )
            check(len(repair_baks) == 1, "one repair backup snapshot")
            manifest = json.loads(
                (repair_baks[0] / "manifest.json").read_text(encoding="utf-8")
            )
            check(str(a_path) in manifest, "manifest covers repaired rollout")
            check(
                (repair_baks[0] / "rollout-a.jsonl").exists(),
                "backup keeps a copy of the rollout",
            )

            # idempotent
            r = run("repair", "task-aaa", "-y", home=home5)
            check(r.returncode == 0, "second repair exit 0")
            check("Sessions to repair: 0" in r.stdout, "second repair is a no-op")

            # --all repairs the remaining session
            r = run("repair", "--all", "-y", home=home5)
            check(r.returncode == 0, "repair --all exit 0")
            check("Repaired: 1 reasoning item(s) in 1 session(s)" in r.stdout, "repair --all fixes remaining")
            c_text = c_path.read_text(encoding="utf-8")
            check('"text": "thinking 0"' not in c_text, "second session reasoning emptied")

            # unknown session id
            r = run("repair", "no-such-session", "-y", home=home5)
            check(r.returncode == 1, "unknown session id exits 1")
            check("No rollout file matches" in r.stderr, "unknown id error message")

            # refuses while Codex is running unless --force
            import types as repair_types

            add_reasoning_history(a_path, 1)
            mod5 = repair_types.ModuleType("codex_api_switch_repair_mod")
            mod5.__file__ = str(SWITCHER)
            with open(SWITCHER, encoding="utf-8") as fh:
                exec(compile(fh.read(), str(SWITCHER), "exec"), mod5.__dict__)
            with mock.patch.dict(os.environ, {"CODEX_SWITCH_HOME": str(home5)}):
                with mock.patch.object(mod5, "is_codex_running", return_value=True):
                    ns = argparse.Namespace(
                        all=False, session="task-aaa", dry_run=False, yes=True, force=False
                    )
                    check(mod5.command_repair(ns) == 3, "repair refuses while running")
                with mock.patch.object(mod5, "is_codex_running", return_value=True):
                    ns = argparse.Namespace(
                        all=False, session="task-aaa", dry_run=False, yes=True, force=True
                    )
                    check(mod5.command_repair(ns) == 0, "repair --force proceeds while running")

        # 15. switching back to OpenAI auto-repairs session history
        with tempfile.TemporaryDirectory(prefix="codex-switch-openai-repair-test-") as tmp6:
            home6 = Path(tmp6)
            setup_home(home6)
            a_path = home6 / "rollout-a.jsonl"
            add_reasoning_history(a_path, 2)
            bak = home6 / "backups" / "codex-api-switch"
            bak.mkdir(parents=True, exist_ok=True)
            (bak / "openai-last.toml").write_text(
                'model_provider = "openai"\nmodel = "gpt-5.5"\n'
            )
            r = run("openai", home=home6)
            check(r.returncode == 0, f"openai switch with auto-repair exit 0 (got {r.returncode})")
            check("Repaired 1 session(s), 2 reasoning item(s)" in r.stdout, "auto-repair reported")
            a_text = a_path.read_text(encoding="utf-8")
            check('"text": "thinking 0"' not in a_text, "auto-repair emptied reasoning content")
            cfg = (home6 / "config.toml").read_text(encoding="utf-8")
            check('model_provider = "openai"' in cfg, "config switched to openai")
            r = run("openai", home=home6)
            check("Already using OpenAI." in r.stderr, "second switch is a no-op")

    print("ALL TESTS PASSED")


if __name__ == "__main__":
    main()
