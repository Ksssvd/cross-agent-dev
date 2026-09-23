# cross-agent-dev

[中文](README.md) | **English**

> Switch between Claude Code, Codex, OpenCode and Factory on the same project — the next agent picks up where the last one left off, without you re-explaining anything.

## The problem

Projects rarely get built by a single coding agent:

- You discuss requirements and architecture in Claude Code, then switch to Codex for the heavy coding.
- Codex runs out of quota halfway through, so you continue in Claude Code or OpenCode.

The new agent can read the code, but it doesn't know **why things were designed this way, which decisions are final, what is really done, what is half-finished, or what comes next**. That knowledge lives only in the previous agent's chat history, so you end up explaining the whole project again.

Worse, quota usually runs out without warning, so the previous agent never gets a chance to hand anything off.

## How it works

The core idea: **don't hand off at the end — keep notes as you go, and keep them in the project folder, not in one agent's chat history.**

| Piece | What it does |
|---|---|
| 11 handoff rules in `AGENTS.md` | Codex, OpenCode and Factory read `AGENTS.md` automatically; Claude Code reads it through `CLAUDE.md`. The rules make every agent **reconcile before starting and record progress while working** |
| `SPEC.md` | What to build: goal, scope, key requirements with acceptance criteria. Rarely changes |
| `STATE.md` | Where things stand: how to verify, task checklist, active decisions with reasons, open questions, known pitfalls, next step. ≤ 80 lines |
| git commit check | Blocks a commit when code has been committed 3 times in a row without updating STATE.md. It's plain git, so it works for every agent — the safety net for "the agent forgot to take notes" |
| `continuity` skill | Three actions: **init** (talk through requirements and create both files), **checkpoint** (update progress and commit before switching agents), **recover** (rebuild missing context from the previous agent's local transcript) |

Source of truth: **code, git and tests > STATE.md > chat history**. When they disagree, the code wins and STATE is corrected.

### What if quota runs out mid-task?

This is the main use case. Open the next agent and say "continue this project". It will:

1. Read `SPEC.md` and `STATE.md`, then check `git status`, `git diff` and recent commits.
2. If STATE is behind the code, read the previous agent's transcript on your machine (Claude Code / Codex), extract decisions and progress, and **verify each item against the code**.
3. Tell you in a few lines — "The last agent finished task 3; task 4 is half done, still missing X; I'll continue from there" — and wait for your OK before touching anything.

## Install

Requires `git`, `python3` (preinstalled on macOS and most Linux distros), and at least one coding agent.

### Option 1: global install (recommended)

Install once and it works for every new project.

```bash
git clone https://github.com/Ksssvd/cross-agent-dev.git ~/cross-agent-dev
```

```bash
~/cross-agent-dev/install.sh --global
```

Then add this line to your global instructions file (`~/.codex/AGENTS.md` for Codex, `~/.claude/CLAUDE.md` for Claude Code — add it to both if you use both):

```markdown
- When starting a project that will be developed over multiple sessions, if it has no SPEC.md and STATE.md, use the continuity skill to set them up first. Skip this for one-off small tasks.
```

> The skill is installed as a symlink, so don't move or delete `~/cross-agent-dev`. To update, run `git -C ~/cross-agent-dev pull`.

### Option 2: install into a single project

```bash
~/cross-agent-dev/install.sh /path/to/your-project
```

If you also use OpenCode or Factory:

```bash
~/cross-agent-dev/install.sh /path/to/your-project --tools claude,opencode,factory
```

This writes the rules straight into the project's `AGENTS.md`, copies the skill into the project (`.agents/skills/continuity`) and installs the git commit check, which is handy for teams. With the global install, the agent does all of this the first time it sets up a project. The installer is safe to re-run: it only touches the parts it manages and leaves your existing `AGENTS.md` / `CLAUDE.md` content alone.

## Usage

No commands to memorize — just talk normally:

| You want to… | Say |
|---|---|
| Start a new project | Create a folder, open any agent and describe what you want, e.g. "I want to build an AI interview-review tool for job seekers…". The agent asks a few key questions, then sets up the files |
| Save progress before switching | "I'm switching agents, save a checkpoint first" |
| Continue in another agent | "Continue this project" |
| Quota ran out before you could save | Just say "continue this project" in the new agent |
| The agent didn't set things up on its own | "Use continuity to set up this project" |

If you're resuming in the *same* tool after your quota resets, its built-in resume is more direct: `claude --continue` or `codex resume`.

### What ends up in your project

```
your-project/
├── AGENTS.md    ← handoff rules (between markers; everything else is yours)
├── CLAUDE.md    ← one line, @AGENTS.md, so Claude Code reads the rules too
├── SPEC.md      ← what to build
└── STATE.md     ← where things stand
```

A typical `STATE.md`:

```markdown
# STATE · updated 2026-09-23 14:20 · by Codex
## Current goal
Finish the subtitle translation pipeline.
## How to verify
- `npm test` — all green
## Tasks
- [x] 1. Video upload and audio extraction
- [~] 2. Transcription — API wired up, timestamp alignment missing (src/asr.ts)
- [ ] 3. Translation
## Active decisions
- D1 Use A instead of B for transcription — B is less accurate on Chinese
## Open questions
- Q1 Should paid users get bulk export?
## Pitfalls
- Videos over 30 min time out; out of scope for now
## Next
Start with timestamp alignment in task 2.
```

## Transcript recovery (recover)

- Supports Claude Code (`~/.claude/projects`) and Codex (`~/.codex/sessions`). **Read-only** — transcripts are never modified.
- Filters out reasoning, tool output and system-injected content. Keeps your own messages, the agent's replies, your answers to multiple-choice questions, and key actions.
- Automatically redacts API keys, tokens and passwords.
- Only the **distilled conclusions** go into STATE; raw chat never lands in git.
- If it can't understand a transcript format, it says so instead of guessing, and falls back to STATE + git.

You can also run it by hand:

```bash
python3 ~/cross-agent-dev/skill/continuity/scripts/recover.py --list
```

```bash
python3 ~/cross-agent-dev/skill/continuity/scripts/recover.py --session 1
```

## git commit check

Rules are advisory, and agents occasionally forget. So there's a deterministic layer in git itself: **when code has been committed 3 times in a row without touching STATE.md, the next commit is blocked** with a note to update STATE first. Agents read the message and fix it themselves.

- Only kicks in once the project uses STATE.md; other projects are unaffected.
- Never overwrites an existing pre-commit hook and leaves custom hook directories (husky, etc.) alone.
- Skip once: `SKIP_STATE_CHECK=1 git commit ...`
- Change the limit: `git config continuity.maxCommitsWithoutState 5` (0 turns it off)

## Supported tools

| Tool | Reads rules from | Reads skills from |
|---|---|---|
| Claude Code | `CLAUDE.md` (imports `AGENTS.md`) | `~/.claude/skills` or `.claude/skills` |
| Codex | `AGENTS.md` | `~/.agents/skills` or `.agents/skills` |
| OpenCode | `AGENTS.md` | `.opencode/skills` (project install with `--tools opencode`) |
| Factory | `AGENTS.md` | `.factory/skills` (project install with `--tools factory`) |

At its core this is just a set of rules and two Markdown files. Any agent that can read files and run git can follow it; the skill is an enhancement, not a requirement.

## Design principles

- **Project state ≠ chat history**: keep only the minimum the next agent needs to continue correctly.
- **Code is the source of truth**: STATE is an index for fast recovery, never a substitute for what the code actually does.
- **Record as you go**: don't rely on an end-of-session handoff; by the time quota runs out it's too late.
- **Vendor-neutral**: no dependency on any particular agent or model, no network access, no API keys.
- **No methodology to learn**: you don't need to know what a spec is; just describe what you want.

## Limitations

- Rules depend on the agent following them, and it may occasionally skip an update. The git commit check, start-of-session reconciliation and transcript recovery exist to catch exactly that.
- It assumes one agent works at a time. Running several agents in parallel means they all edit the same STATE.md, which invites conflicts.
- Transcript recovery currently supports Claude Code and Codex only, and may need updating if either tool changes its log format.
- The rules, templates and skill instructions are currently written in Chinese. Agents handle them fine, but they're less readable for English-speaking humans. English versions are welcome.

## Development

```bash
python3 -m unittest discover tests
```

Manual end-to-end scenarios with real agents are in [tests/scenarios/README.md](tests/scenarios/README.md). Issues and PRs welcome.

## License

[MIT](LICENSE)
