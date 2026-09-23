#!/usr/bin/env python3
"""Read the previous coding agent's local transcript and print a compact,
redacted excerpt, so the next agent can rebuild STATE.md.

Supports Claude Code (~/.claude/projects) and Codex (~/.codex/sessions).
Read-only. Standard library only.

Usage:
  recover.py --list                 # candidate sessions for this project
  recover.py                        # excerpt of the most recent previous session
  recover.py --session <id|path>    # excerpt of a specific session
  recover.py --filter keyword       # keep decision/progress-like messages + the tail
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

CURRENT_WINDOW_SECONDS = 15 * 60
MESSAGE_CHAR_LIMIT = 1200
DEFAULT_BUDGET = 30000
TAIL_ALWAYS_KEEP = 12

# Injected context that is not part of the real conversation.
NOISE_PREFIXES = (
    "<environment_context>",
    "<user_instructions>",
    "<permissions",
    "# AGENTS.md instructions",
    "<command-",
    "<local-command",
    "<system-reminder>",
    "Caveat:",
    "<task-notification>",
    "<heartbeat>",
    "<recommended_plugins>",
    "<external_codex_apps",
    "<image",
    "</image>",
)

KEYWORDS = re.compile(
    r"决定|决策|改用|不用|放弃|换成|选用|采用|原因|因为|完成|做完|搞定|进度|还差|没做|待做|"
    r"下一步|接下来|bug|报错|失败|问题|坑|风险|TODO|注意|别|不要|"
    r"decid|decision|instead|chose|switch|reject|done|finish|complet|todo|next|fail|error|bug|block|caveat",
    re.IGNORECASE,
)

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{16,}"),
    re.compile(
        r"(?i)((?:api[_-]?key|secret|token|password|passwd|pwd|access[_-]?key)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]{6,}"
    ),
]


@dataclass
class Message:
    role: str  # user | assistant | action
    text: str
    ts: datetime | None = None


@dataclass
class Session:
    tool: str  # claude | codex
    path: Path
    session_id: str
    cwd: str
    mtime: float
    first_user: str = ""
    is_current: bool = False
    messages: list[Message] = field(default_factory=list)


# ---------- helpers ----------

def parse_ts(value) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone()
    except ValueError:
        return None


def read_jsonl(path: Path, limit: int | None = None):
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if limit is not None and i >= limit:
                    return
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except OSError:
        return


def in_project(cwd: str, project: Path) -> bool:
    if not cwd:
        return False
    try:
        c = Path(cwd).resolve()
    except OSError:
        return False
    return c == project or project in c.parents


def is_noise(text: str) -> bool:
    return text.lstrip().startswith(NOISE_PREFIXES)


def redact(text: str) -> str:
    for pat in SECRET_PATTERNS:
        if pat.groups:
            text = pat.sub(lambda m: m.group(1) + "[已脱敏]", text)
        else:
            text = pat.sub("[已脱敏]", text)
    return text


def shorten(text: str, limit: int = MESSAGE_CHAR_LIMIT) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    tail = limit - head
    return f"{text[:head]}\n…（省略 {len(text) - limit} 字）…\n{text[-tail:]}"


def action_summary(name: str, args) -> str:
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            return f"{name}: {args[:100]}"
    if not isinstance(args, dict):
        return name
    for key in ("file_path", "path", "command", "cmd", "pattern", "description"):
        val = args.get(key)
        if val:
            if isinstance(val, list):
                val = " ".join(str(v) for v in val)
            return f"{name}: {str(val)[:100]}"
    return name


# ---------- Claude Code ----------

# Tools whose result is the user's own answer (e.g. a multiple-choice decision).
USER_ANSWER_TOOLS = {"AskUserQuestion"}


def tool_result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def claude_text_blocks(content, role: str, tool_names: dict) -> tuple[list[str], list[str]]:
    texts, actions = [], []
    if isinstance(content, str):
        texts.append(content)
    elif isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")
            if kind == "text":
                texts.append(block.get("text") or "")
            elif kind == "tool_use" and role == "assistant":
                name = block.get("name") or "tool"
                tool_names[block.get("id")] = name
                if name in USER_ANSWER_TOOLS:
                    questions = (block.get("input") or {}).get("questions") or []
                    q = "；".join(x.get("question", "") for x in questions if isinstance(x, dict))
                    texts.append(f"（向用户提问）{q}")
                else:
                    actions.append(action_summary(name, block.get("input")))
            elif kind == "tool_result" and tool_names.get(block.get("tool_use_id")) in USER_ANSWER_TOOLS:
                texts.append(f"（用户的选择）{tool_result_text(block)}")
    return texts, actions


def claude_sessions(root: Path, project: Path) -> list[Session]:
    if not root.is_dir():
        return []
    encoded = re.sub(r"[^A-Za-z0-9]", "-", str(project))
    preferred = [d for d in root.iterdir() if d.is_dir() and d.name == encoded]
    dirs = preferred or [d for d in root.iterdir() if d.is_dir()]
    found = []
    for d in dirs:
        for path in d.glob("*.jsonl"):
            cwd = ""
            for obj in read_jsonl(path, limit=50):
                if isinstance(obj.get("cwd"), str):
                    cwd = obj["cwd"]
                    break
            if in_project(cwd, project):
                found.append(Session("claude", path, path.stem, cwd, path.stat().st_mtime))
    if not found and preferred:
        # The encoded directory can differ from cwd (e.g. repo root); fall back to a full scan.
        return claude_sessions_full(root, project)
    return found


def claude_sessions_full(root: Path, project: Path) -> list[Session]:
    found = []
    for path in root.glob("*/*.jsonl"):
        for obj in read_jsonl(path, limit=50):
            if isinstance(obj.get("cwd"), str):
                if in_project(obj["cwd"], project):
                    found.append(Session("claude", path, path.stem, obj["cwd"], path.stat().st_mtime))
                break
    return found


def load_claude(session: Session) -> None:
    tool_names: dict = {}
    for obj in read_jsonl(session.path):
        kind = obj.get("type")
        if kind not in ("user", "assistant") or obj.get("isSidechain") or obj.get("isMeta"):
            continue
        msg = obj.get("message") or {}
        role = msg.get("role") or kind
        texts, actions = claude_text_blocks(msg.get("content"), role, tool_names)
        ts = parse_ts(obj.get("timestamp"))
        for t in texts:
            if t.strip() and not is_noise(t):
                session.messages.append(Message(role, t, ts))
        for a in actions:
            session.messages.append(Message("action", a, ts))


# ---------- Codex ----------

def codex_sessions(root: Path, project: Path) -> list[Session]:
    if not root.is_dir():
        return []
    found = []
    for path in root.rglob("rollout-*.jsonl"):
        meta = next(read_jsonl(path, limit=1), None)
        if not meta or meta.get("type") != "session_meta":
            continue
        payload = meta.get("payload") or {}
        source = payload.get("source")
        if isinstance(source, dict) and source.get("subagent"):
            continue  # subagent threads belong to a root session
        cwd = payload.get("cwd") or ""
        if in_project(cwd, project):
            sid = payload.get("id") or path.stem
            found.append(Session("codex", path, sid, cwd, path.stat().st_mtime))
    return found


def load_codex(session: Session) -> None:
    for obj in read_jsonl(session.path):
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload") or {}
        ts = parse_ts(obj.get("timestamp"))
        kind = payload.get("type")
        if kind == "message":
            role = payload.get("role")
            if role not in ("user", "assistant"):
                continue
            for block in payload.get("content") or []:
                if not isinstance(block, dict):
                    continue
                text = block.get("text") or ""
                if text.strip() and not is_noise(text):
                    session.messages.append(Message(role, text, ts))
        elif kind in ("function_call", "custom_tool_call", "local_shell_call"):
            args = payload.get("arguments") or payload.get("input") or payload.get("action")
            session.messages.append(Message("action", action_summary(payload.get("name") or kind, args), ts))


# ---------- selection ----------

def detect_current_tool() -> str | None:
    if os.environ.get("CLAUDECODE") == "1":
        return "claude"
    if any(k.startswith("CODEX_") for k in os.environ if k != "CODEX_HOME"):
        return "codex"
    return None


def find_sessions(args, project: Path) -> list[Session]:
    claude_root = Path(args.claude_dir or Path.home() / ".claude" / "projects")
    codex_root = Path(args.codex_dir or Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "sessions")
    sessions = claude_sessions(claude_root, project) + codex_sessions(codex_root, project)
    sessions.sort(key=lambda s: s.mtime, reverse=True)

    current = args.current_tool or detect_current_tool()
    if current:
        now = time.time()
        for s in sessions:
            if s.tool == current:
                s.is_current = now - s.mtime < CURRENT_WINDOW_SECONDS
                break
    return sessions


def load(session: Session) -> None:
    (load_claude if session.tool == "claude" else load_codex)(session)
    for m in session.messages:
        if m.role == "user":
            session.first_user = m.text.strip().splitlines()[0][:80] if m.text.strip() else ""
            break


def pick_messages(messages: list[Message], mode: str, budget: int) -> list[int]:
    """Choose which messages fit into the budget.

    `mode` is the extension point for smarter pre-filters (e.g. a small
    classifier model judging each message) — each mode only has to return a subset in order.
    Returns indices into `messages`, in order.
    """
    if not messages:
        return []
    keep = [False] * len(messages)
    first_user = next((i for i, m in enumerate(messages) if m.role == "user"), None)
    if first_user is not None:
        keep[first_user] = True
    for i in range(max(0, len(messages) - TAIL_ALWAYS_KEEP), len(messages)):
        keep[i] = True
    if mode == "keyword":
        for i, m in enumerate(messages):
            if m.role != "action" and KEYWORDS.search(m.text):
                keep[i] = True
    else:  # tail: everything, newest first, until the budget runs out
        keep = [True] * len(messages)

    chosen, used = [], 0
    # Always spend budget on the first request and the tail first, then fill backwards.
    order = ([first_user] if first_user is not None else []) + list(range(len(messages) - 1, -1, -1))
    seen = set()
    for i in order:
        if i in seen or not keep[i]:
            continue
        seen.add(i)
        cost = len(shorten(messages[i].text)) + 20
        if used + cost > budget and chosen:
            continue
        chosen.append(i)
        used += cost
    return sorted(chosen)


# ---------- output ----------

TOOL_NAMES = {"claude": "Claude Code", "codex": "Codex"}
ROLE_NAMES = {"user": "用户", "assistant": "Agent", "action": "操作"}


def fmt_time(ts: float | datetime | None) -> str:
    if ts is None:
        return "?"
    if isinstance(ts, float):
        ts = datetime.fromtimestamp(ts)
    return ts.strftime("%m-%d %H:%M")


def print_list(sessions: list[Session]) -> None:
    if not sessions:
        print("没有找到这个项目的 Claude Code / Codex 对话记录。")
        return
    print("| # | 工具 | 最后活动 | 第一句话 | 备注 |")
    print("|---|---|---|---|---|")
    for i, s in enumerate(sessions[:15], 1):
        load(s)
        note = "可能是当前对话" if s.is_current else ""
        first = redact(s.first_user).replace("|", "/")
        print(f"| {i} | {TOOL_NAMES[s.tool]} | {fmt_time(s.mtime)} | {first} | {note} |")
    print("\n用 --session <编号或会话 id> 指定一个。")


def print_excerpt(s: Session, mode: str, budget: int) -> None:
    chosen = pick_messages(s.messages, mode, budget)
    start = s.messages[0].ts if s.messages else None
    end = s.messages[-1].ts if s.messages else None
    print("# 上个 Agent 的对话摘录（recover）\n")
    print(f"- 来源：{TOOL_NAMES[s.tool]} · {fmt_time(start)} → {fmt_time(end)} · 会话 {s.session_id}")
    print(f"- 共 {len(s.messages)} 条，摘录 {len(chosen)} 条（模式 {mode}，预算 {budget} 字），已自动脱敏")
    print("\n> 这是原始材料，不是结论。只提炼：最终决定和原因、任务进度、做了一半的事、坑、下一步。")
    print("> 前后矛盾时以时间靠后的为准；写进 STATE 前先和代码、git、测试核对。不要把原文抄进 STATE。\n")
    last = -1
    for idx in chosen:
        m = s.messages[idx]
        if last >= 0 and idx > last + 1:
            print(f"_…（跳过 {idx - last - 1} 条）…_\n")
        last = idx
        if m.role == "action":
            print(f"- [{fmt_time(m.ts)}] 操作 · {redact(m.text)}")
            continue
        print(f"\n### [{fmt_time(m.ts)}] {ROLE_NAMES[m.role]}\n")
        print(redact(shorten(m.text)))
        print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="从上个 Agent 的本地对话记录里摘录交接材料")
    ap.add_argument("--project", default=".", help="项目目录（默认当前目录）")
    ap.add_argument("--list", action="store_true", help="列出候选对话")
    ap.add_argument("--session", help="编号（来自 --list）、会话 id 前缀或文件路径")
    ap.add_argument("--filter", choices=["tail", "keyword"], default="tail", dest="mode")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="输出字数上限")
    ap.add_argument("--include-current", action="store_true", help="允许选中当前正在进行的对话")
    ap.add_argument("--current-tool", choices=["claude", "codex"], help="手动指定当前所在工具")
    ap.add_argument("--claude-dir", help=argparse.SUPPRESS)
    ap.add_argument("--codex-dir", help=argparse.SUPPRESS)
    args = ap.parse_args(argv)

    project = Path(args.project).resolve()
    sessions = find_sessions(args, project)

    if args.list:
        print_list(sessions)
        return 0

    target = None
    if args.session:
        if args.session.isdigit() and 1 <= int(args.session) <= len(sessions):
            target = sessions[int(args.session) - 1]
        else:
            for s in sessions:
                if s.session_id.startswith(args.session) or str(s.path) == args.session:
                    target = s
                    break
        if target is None:
            print(f"找不到会话：{args.session}。先用 --list 查看。", file=sys.stderr)
            return 1
    else:
        candidates = [s for s in sessions if args.include_current or not s.is_current]
        if not candidates:
            print("没有找到上一个 Agent 的对话记录（只有当前对话，或记录不在本机）。", file=sys.stderr)
            return 1
        target = candidates[0]

    load(target)
    if not target.messages:
        print(f"对话记录格式没读懂或是空的：{target.path}。不要猜，改用 STATE + git 恢复。", file=sys.stderr)
        return 2
    print_excerpt(target, args.mode, args.budget)
    return 0


if __name__ == "__main__":
    sys.exit(main())
