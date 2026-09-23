# cross-agent-dev

**中文** | [English](README.en.md)

> 在 Claude Code、Codex、OpenCode、Factory 之间换着开发同一个项目，新 Agent 不用你重新解释，就能接着干。

## 解决什么问题

一个项目常常不会只用一个 Coding Agent 做完：

- 在 Claude Code 里讨论需求、定方案，再切到 Codex 写代码；
- Codex 做到一半额度用完了，换 Claude Code 或 OpenCode 接着做。

换过去以后，新 Agent 看得到代码，却不知道**为什么这么设计、定过哪些决定、哪些功能真的做完了、哪个做到一半、下一步该干什么**。这些信息只存在于上一个 Agent 的聊天记录里，于是你只能从头再讲一遍。

更麻烦的是：额度常常是突然用完的，上一个 Agent 根本没机会"交接"。

## 它怎么做

核心思路是：**不在结束时交接，而是边做边记。并且把记录放在项目文件夹里，而不是某个 Agent 的聊天记录里。**

| 组成 | 作用 |
|---|---|
| `AGENTS.md` 里的 11 条接力规则 | Codex、OpenCode、Factory 开工时会自动读，Claude Code 通过 `CLAUDE.md` 引用。规则让每个 Agent **开工先对账，干活边做边记** |
| `SPEC.md` | 要做什么：目标、范围、关键需求和验收标准。很少变 |
| `STATE.md` | 做到哪了：验证方式、任务勾选清单、有效决定和原因、待确认问题、坑、下一步。≤ 80 行 |
| git 提交检查 | 连续 3 次提交代码却没更新 STATE.md 时拦下提交。它是 git 自己的机制，对所有 Agent 都生效，用来兜底"Agent 忘了记" |
| `continuity` skill | 三个动作：**建档**（和你聊需求，生成上面两个文件）、**存档**（换 Agent 前更新进度并提交）、**补交接**（从上个 Agent 的本地聊天记录里补回遗漏的信息） |

信息可信度：**代码、git、测试 > STATE.md > 聊天记录**。两者冲突时以代码为准，并修正 STATE。

### 额度突然用完怎么办？

这是它最重要的场景。换到新 Agent 后说一句"继续这个项目"，新 Agent 会：

1. 读 SPEC.md 和 STATE.md，看 `git status`、`git diff`、最近的 commit；
2. 发现 STATE 落后于代码时，读取上个 Agent 在你电脑上的聊天记录（Claude Code / Codex），提炼出决定和进度，**再和代码逐条核对**；
3. 先用几句话告诉你："上个 Agent 做到第 3 项，第 4 项做了一半，还差 X，我从这里继续。"你确认后它才开始动手。

## 安装

需要：`git`、`python3`（macOS 和大多数 Linux 自带），以及至少一个 Coding Agent。

### 方式一：全局安装（推荐）

装一次，以后所有新项目都自动生效。

```bash
git clone https://github.com/Ksssvd/cross-agent-dev.git ~/cross-agent-dev
```

```bash
~/cross-agent-dev/install.sh --global
```

然后把下面这行加进你的全局规则文件（Codex 用 `~/.codex/AGENTS.md`，Claude Code 用 `~/.claude/CLAUDE.md`，两个都用就都加）：

```markdown
- 开始开发一个需要多次迭代的项目时，若项目里没有 SPEC.md 和 STATE.md，先用 continuity skill 建档；一次性的小任务不用。
```

> Skill 是通过软链接安装的，请不要移动或删除 `~/cross-agent-dev` 文件夹。更新时运行 `git -C ~/cross-agent-dev pull` 即可。

### 方式二：只装进某个项目

```bash
~/cross-agent-dev/install.sh /path/to/your-project
```

也用 OpenCode 或 Factory 的话：

```bash
~/cross-agent-dev/install.sh /path/to/your-project --tools claude,opencode,factory
```

这种方式会把规则直接写进项目的 `AGENTS.md`，Skill 也复制进项目（`.agents/skills/continuity`），并装上 git 提交检查，适合团队共享。全局安装时，这些会在 Agent 第一次给项目建档时自动完成。安装脚本可以重复运行，只会改它自己管理的部分，不会动你原有的 `AGENTS.md`、`CLAUDE.md` 内容。

## 使用

不用记任何命令，正常说话就行：

| 你想… | 你说 |
|---|---|
| 开始一个新项目 | 新建文件夹，打开任意 Agent，直接描述需求，比如"我想做一个 AI 面试复盘工具，给求职者用……"。Agent 会先问几个关键问题，然后建档 |
| 换 Agent 前存个档 | "我要换 Agent 了，先存个档" |
| 在新 Agent 里接着做 | "继续这个项目" |
| 额度突然用完、没来得及存档 | 换过去照样说"继续这个项目" |
| Agent 没有主动建档 | "用 continuity 建档" |

如果是同一个工具额度恢复后继续，用工具自带的恢复功能更直接：`claude --continue` 或 `codex resume`。

### 装好后项目里会有什么

```
your-project/
├── AGENTS.md    ← 接力规则（在标记之间，其余内容是你自己的）
├── CLAUDE.md    ← 一行 @AGENTS.md，让 Claude Code 也读规则
├── SPEC.md      ← 要做什么
└── STATE.md     ← 做到哪了
```

`STATE.md` 大概长这样：

```markdown
# STATE · 更新：2026-09-23 14:20 · by Codex
## 当前目标
完成字幕翻译主流程。
## 验证方式
- `npm test` —— 全部通过
## 任务清单
- [x] 1. 视频上传与抽音轨
- [~] 2. 语音转写 —— 已接好接口，差时间轴对齐（src/asr.ts）
- [ ] 3. 翻译
## 有效决定
- D1 转写用 A 不用 B —— B 中文准确率差
## 待确认问题
- Q1 付费用户是否支持批量导出？
## 坑 / 已知问题
- 超过 30 分钟的视频会超时，先不处理
## 下一步
从任务 2 的时间轴对齐开始。
```

## 读聊天记录兜底（recover）

- 支持 Claude Code（`~/.claude/projects`）和 Codex（`~/.codex/sessions`）。**只读**，不修改任何记录。
- 会过滤掉思考过程、工具输出和系统自动注入的内容；保留你的原话、Agent 的回复、你在选择题里做的选择，以及关键操作。
- 密钥、token、密码等会被自动脱敏。
- 只把**提炼出的结论**写进 STATE，聊天原文不会进 git。
- 格式读不懂时直接报错，不瞎猜，改用 STATE + git 恢复。

也可以手动查看：

```bash
python3 ~/cross-agent-dev/skill/continuity/scripts/recover.py --list
```

```bash
python3 ~/cross-agent-dev/skill/continuity/scripts/recover.py --session 1
```

## git 提交检查

规则是"建议"，Agent 偶尔会忘。所以再加一道 git 自己的检查：**连续 3 次提交都改了代码、却没更新 STATE.md 时，拦下这次提交**，提示先更新 STATE。Agent 看到提示会自己补上。

- 只在项目用了 STATE.md 之后才生效，普通项目不受影响。
- 不会覆盖你已有的 pre-commit，也不碰 husky 等自定义 hooks 目录。
- 跳过一次：`SKIP_STATE_CHECK=1 git commit ...`
- 调整次数：`git config continuity.maxCommitsWithoutState 5`（设为 0 关闭）

## 支持的工具

| 工具 | 读规则 | 读 Skill |
|---|---|---|
| Claude Code | `CLAUDE.md`（引用 `AGENTS.md`） | `~/.claude/skills` 或 `.claude/skills` |
| Codex | `AGENTS.md` | `~/.agents/skills` 或 `.agents/skills` |
| OpenCode | `AGENTS.md` | `.opencode/skills`（项目安装时加 `--tools opencode`） |
| Factory | `AGENTS.md` | `.factory/skills`（项目安装时加 `--tools factory`） |

核心只有规则和两个 Markdown 文件。任何能读文件、能运行 git 的 Agent 都能遵守；Skill 只是锦上添花。

## 设计原则

- **项目状态 ≠ 聊天记录**：只保留"让下一个 Agent 正确接着做"所需的最少信息。
- **代码为准**：STATE 只是快速恢复进度的索引，不能替代代码事实。
- **边做边记**：不依赖结束时交接，因为额度用完那一刻已经来不及了。
- **不绑定任何一家**：不依赖某个 Agent、某个模型，也不需要联网或 API Key。
- **用户不用学方法论**：你不需要知道什么是 Spec，正常聊需求就行。

## 局限

- 规则靠 Agent 自觉遵守，偶尔可能漏记。git 提交检查、开工对账和读聊天记录兜底就是为这种情况准备的。
- 同一时间只适合一个 Agent 在干活。如果同时开多个 Agent 并行开发，它们会同时改同一个 STATE.md，容易冲突。
- 读聊天记录目前只支持 Claude Code 和 Codex。这两个工具升级后如果改了记录格式，可能需要更新脚本。
- 规则和模板目前是中文写的。各家 Agent 都能正常理解，只是英文用户读起来不太直观。

## 开发

```bash
python3 -m unittest discover tests
```

真实跨 Agent 的手动验收步骤见 [tests/scenarios/README.md](tests/scenarios/README.md)。欢迎提 Issue 和 PR。

## 许可证

[MIT](LICENSE)
