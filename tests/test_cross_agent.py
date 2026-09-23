"""Tests for recover.py and install.sh.  Run: python3 -m unittest discover tests"""

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skill" / "continuity" / "scripts"))
import recover  # noqa: E402

FAKE_KEY = "sk-" + "a1B2c3D4e5F6g7H8i9J0kLmN"


def write_jsonl(path: Path, rows, mtime=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def claude_rows(cwd):
    return [
        {"type": "user", "cwd": cwd, "timestamp": "2026-09-23T06:00:00Z",
         "message": {"role": "user", "content": "帮我做一个短剧翻译工具"}},
        {"type": "user", "cwd": cwd, "timestamp": "2026-09-23T06:00:01Z", "isMeta": True,
         "message": {"role": "user", "content": "<system-reminder>ignore</system-reminder>"}},
        {"type": "assistant", "cwd": cwd, "timestamp": "2026-09-23T06:01:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "thinking", "thinking": "secret reasoning"},
             {"type": "text", "text": f"决定：ASR 用 Whisper，不用 X，因为中文更准。key={FAKE_KEY}"},
             {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/asr.ts"}},
         ]}},
        {"type": "user", "cwd": cwd, "timestamp": "2026-09-23T06:01:05Z",
         "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
        {"type": "assistant", "cwd": cwd, "timestamp": "2026-09-23T06:03:00Z",
         "message": {"role": "assistant", "content": [
             {"type": "tool_use", "id": "q1", "name": "AskUserQuestion",
              "input": {"questions": [{"question": "字幕用哪种样式？"}]}}]}},
        {"type": "user", "cwd": cwd, "timestamp": "2026-09-23T06:03:30Z",
         "message": {"role": "user", "content": [
             {"type": "tool_result", "tool_use_id": "q1", "content": "选了：底部双语字幕"}]}},
        {"type": "assistant", "cwd": cwd, "isSidechain": True, "timestamp": "2026-09-23T06:02:00Z",
         "message": {"role": "assistant", "content": [{"type": "text", "text": "subagent chatter"}]}},
    ]


def codex_rows(cwd, source="cli"):
    return [
        {"type": "session_meta", "timestamp": "2026-09-23T07:00:00Z",
         "payload": {"id": "codex-abc123", "cwd": cwd, "source": source}},
        {"type": "response_item", "timestamp": "2026-09-23T07:00:01Z",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "<environment_context>cwd</environment_context>"}]}},
        {"type": "response_item", "timestamp": "2026-09-23T07:00:02Z",
         "payload": {"type": "message", "role": "user",
                     "content": [{"type": "input_text", "text": "继续做翻译模块"}]}},
        {"type": "response_item", "timestamp": "2026-09-23T07:01:00Z",
         "payload": {"type": "function_call", "name": "shell",
                     "arguments": json.dumps({"command": ["npm", "test"]})}},
        {"type": "response_item", "timestamp": "2026-09-23T07:02:00Z",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "翻译接口做完一半，还差批量重试。"}]}},
    ]


class RecoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.project = base / "my project"
        (self.project / "src").mkdir(parents=True)
        self.claude = base / "claude"
        self.codex = base / "codex"
        cwd = str(self.project.resolve())
        now = time.time()
        write_jsonl(self.claude / "-whatever" / "s1.jsonl", claude_rows(cwd), mtime=now - 3600)
        write_jsonl(self.codex / "2026/09/23/rollout-1.jsonl", codex_rows(cwd), mtime=now - 60)
        write_jsonl(self.codex / "2026/09/23/rollout-sub.jsonl",
                    codex_rows(cwd, source={"subagent": {"thread_spawn": {}}}), mtime=now)
        write_jsonl(self.codex / "2026/09/23/rollout-other.jsonl", codex_rows("/elsewhere"), mtime=now)

    def tearDown(self):
        self.tmp.cleanup()

    def run_recover(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        args = ["--project", str(self.project), "--claude-dir", str(self.claude),
                "--codex-dir", str(self.codex), *extra]
        with redirect_stdout(out), redirect_stderr(err):
            code = recover.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_list_finds_only_this_projects_root_sessions(self):
        code, out, _ = self.run_recover("--list", "--current-tool", "claude")
        self.assertEqual(code, 0)
        rows = [l for l in out.splitlines() if l[:3] in ("| 1", "| 2", "| 3")]
        self.assertEqual(len(rows), 2)  # subagent + other-project sessions excluded
        self.assertIn("Codex", rows[0])  # newest first
        self.assertIn("帮我做一个短剧翻译工具", rows[1])

    def test_skips_current_session_of_current_tool(self):
        code, out, _ = self.run_recover("--current-tool", "codex")
        self.assertEqual(code, 0)
        self.assertIn("来源：Claude Code", out)

    def test_claude_excerpt_filters_noise_and_redacts(self):
        code, out, _ = self.run_recover("--session", "s1")
        self.assertEqual(code, 0)
        self.assertIn("ASR 用 Whisper", out)
        self.assertIn("操作 · Edit: src/asr.ts", out)
        self.assertIn("（向用户提问）字幕用哪种样式？", out)
        self.assertIn("（用户的选择）选了：底部双语字幕", out)
        self.assertNotIn(FAKE_KEY, out)
        self.assertIn("[已脱敏]", out)
        for hidden in ("secret reasoning", "system-reminder", "subagent chatter", "tool_result"):
            self.assertNotIn(hidden, out)

    def test_codex_excerpt(self):
        code, out, _ = self.run_recover("--session", "codex-abc")
        self.assertEqual(code, 0)
        self.assertIn("继续做翻译模块", out)
        self.assertIn("还差批量重试", out)
        self.assertIn("操作 · shell: npm test", out)
        self.assertNotIn("environment_context", out)

    def test_unknown_session(self):
        code, _, err = self.run_recover("--session", "nope")
        self.assertEqual(code, 1)
        self.assertIn("找不到会话", err)

    def test_unreadable_format_does_not_guess(self):
        write_jsonl(self.codex / "2026/09/24/rollout-new.jsonl",
                    [{"type": "session_meta", "payload": {"id": "weird", "cwd": str(self.project.resolve())}},
                     {"type": "brand_new_format", "payload": {}}], mtime=time.time() + 10)
        code, _, err = self.run_recover("--session", "weird")
        self.assertEqual(code, 2)
        self.assertIn("格式没读懂", err)


class PickMessagesTest(unittest.TestCase):
    def test_budget_keeps_first_request_and_tail(self):
        msgs = [recover.Message("user", "最初的需求")] + [
            recover.Message("assistant", f"闲聊 {i} " + "x" * 500) for i in range(50)
        ] + [recover.Message("assistant", "决定：改用方案 C，因为 A 太慢")] + [
            recover.Message("assistant", f"收尾 {i}") for i in range(3)
        ]
        tail = recover.pick_messages(msgs, "tail", budget=3000)
        self.assertIn(0, tail)
        self.assertIn(len(msgs) - 1, tail)
        self.assertLess(len(tail), len(msgs))

        kw = recover.pick_messages(msgs, "keyword", budget=100000)
        self.assertIn(0, kw)
        self.assertIn(51, kw)  # the decision
        self.assertNotIn(1, kw)  # plain chatter outside the tail

    def test_redact_patterns(self):
        text = f"api_key: {FAKE_KEY}\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz\npassword=hunter2hunter2"
        out = recover.redact(text)
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", out)
        self.assertNotIn("hunter2hunter2", out)


class InstallTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.target = Path(self.tmp.name) / "proj"
        self.target.mkdir()
        subprocess.run(["git", "init", "-q", str(self.target)], check=True)

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, *extra):
        return subprocess.run(["bash", str(ROOT / "install.sh"), str(self.target), *extra],
                              capture_output=True, text=True)

    def test_fresh_install_and_idempotent_rerun(self):
        (self.target / "AGENTS.md").write_text("# 我的项目规则\n不要删我\n", encoding="utf-8")
        r = self.install("--tools", "claude,opencode")
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.install("--tools", "claude,opencode")
        self.assertEqual(r.returncode, 0, r.stderr)

        agents = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("不要删我", agents)
        self.assertEqual(agents.count("cross-agent-dev:start"), 1)
        self.assertIn("跨 Agent 接力规则", agents)

        claude_md = (self.target / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertEqual(claude_md.splitlines().count("@AGENTS.md"), 1)

        skill = self.target / ".agents/skills/continuity/SKILL.md"
        self.assertTrue(skill.is_file())
        for tool in ("claude", "opencode"):
            link = self.target / f".{tool}/skills/continuity"
            self.assertTrue(link.is_symlink())
            self.assertTrue((link / "SKILL.md").is_file())
        self.assertFalse((self.target / ".factory").exists())

    def test_updates_existing_block_in_place(self):
        (self.target / "AGENTS.md").write_text(
            "前\n<!-- cross-agent-dev:start -->\n旧规则\n<!-- cross-agent-dev:end -->\n后\n", encoding="utf-8")
        r = self.install()
        self.assertEqual(r.returncode, 0, r.stderr)
        agents = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertNotIn("旧规则", agents)
        self.assertTrue(agents.startswith("前\n"))
        self.assertTrue(agents.rstrip().endswith("后"))
        self.assertEqual(agents.count("cross-agent-dev:end"), 1)

    def test_global_install_is_idempotent_and_safe(self):
        home = Path(self.tmp.name) / "home"
        (home / ".agents/skills/continuity").mkdir(parents=True)  # someone else's skill
        env = {**os.environ, "HOME": str(home)}
        for _ in range(2):
            r = subprocess.run(["bash", str(ROOT / "install.sh"), "--global"],
                               capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stderr)
        link = home / ".claude/skills/continuity"
        self.assertTrue(link.is_symlink())
        self.assertTrue((link / "SKILL.md").is_file())
        self.assertFalse((home / ".agents/skills/continuity").is_symlink())  # left untouched
        self.assertIn("已存在且指向别处", r.stderr)

    def test_refuses_broken_markers(self):
        original = "<!-- cross-agent-dev:start -->\n重要内容\n"
        (self.target / "AGENTS.md").write_text(original, encoding="utf-8")
        r = self.install()
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual((self.target / "AGENTS.md").read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
