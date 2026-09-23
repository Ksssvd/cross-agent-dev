# cross-agent-dev · 跨 Agent 开发接力

在 Claude Code、Codex、OpenCode、Factory 之间换着开发同一个项目时，新 Agent 不用你重新解释，自己就能搞清楚**要做什么、做到哪、为什么这么做、下一步干嘛**。

## 它怎么工作

装进项目后，项目里会多出这些东西：

| 文件 | 作用 |
|---|---|
| `AGENTS.md` 里的 10 条规则 | 所有 Agent 开工时自动读取：先对账再动手，边做边记 |
| `SPEC.md` | 要做什么（Agent 和你聊需求时自动生成） |
| `STATE.md` | 做到哪了：任务清单、有效决定、坑、下一步（Agent 边做边更新） |
| `.agents/skills/continuity/` | 可选加强：建档、存档，以及从上个 Agent 的聊天记录里补交接 |

可信度排序：**代码、git、测试 > STATE > 聊天记录**。

## 安装

**推荐：全局安装一次，之后所有新项目自动生效。**

1. 把 Skill 软链接到全局目录（Claude Code 读 `~/.claude/skills`，Codex 读 `~/.agents/skills`）：

   ```bash
   ln -s "$(pwd)/skill/continuity" ~/.claude/skills/continuity
   ```

   ```bash
   ln -s "$(pwd)/skill/continuity" ~/.agents/skills/continuity
   ```

2. 在全局规则文件（`~/.codex/AGENTS.md`，或 `~/.claude/CLAUDE.md`）里加一行：

   > 开始开发一个需要多次迭代的项目时，若项目里没有 SPEC.md 和 STATE.md，先用 continuity skill 建档；一次性的小任务不用。

之后新建文件夹、打开任意 Agent、直接说需求就行。建档时 Agent 会自己把接力规则写进项目的 `AGENTS.md`。

**或者：只装进单个项目**

```bash
./install.sh /path/to/your-project
```

也用 OpenCode 或 Factory 的话：

```bash
./install.sh /path/to/your-project --tools claude,opencode,factory
```

可以重复运行，更新规则时也用这条命令。它只改自己管理的部分，你原有的 `AGENTS.md`、`CLAUDE.md` 内容不会动。

## 日常怎么用

不用记任何命令，正常说话就行：

| 你想… | 你说 |
|---|---|
| 开始一个新项目 | 正常描述要做什么，比如"我要做一个 AI 短剧翻译工具" |
| 换 Agent 前存个档 | "我要换 Agent 了，先存个档" |
| 在新 Agent 里接着做 | "继续这个项目" |
| 额度突然用完、没来得及存档 | 换过去照样说"继续这个项目"，它会发现 STATE 落后，自动去读上个 Agent 的聊天记录补上 |

同一个工具在额度恢复后继续干活，用工具自带的恢复功能更直接：

```bash
claude --continue
```

```bash
codex resume
```

## 读聊天记录兜底（recover）

- 支持 Claude Code（`~/.claude/projects`）和 Codex（`~/.codex/sessions`）。只读，不改任何记录。
- 会过滤掉思考过程、工具输出、系统自动注入的内容；密钥、token、密码会被自动脱敏。
- 只把提炼出的结论写进 STATE，原文不进 git。
- 格式读不懂时直接报错，不瞎猜，改用 STATE + git 恢复。

手动查看：

```bash
python3 .agents/skills/continuity/scripts/recover.py --list
```

## 开发

```bash
python3 -m unittest discover tests
```

真实跨 Agent 的手动验收步骤见 [tests/scenarios/README.md](tests/scenarios/README.md)。
