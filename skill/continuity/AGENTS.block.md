<!-- cross-agent-dev:start -->
## 跨 Agent 接力规则
本项目可能由多个 Coding Agent 轮流开发。SPEC.md = 要做什么，STATE.md = 做到哪了。两者都以代码、git、测试为准。
**开工时**
1. 先读 SPEC.md 和 STATE.md，再看 git status、git diff、最近 5 条 git log。两个文件不存在时，先用 continuity skill 的 init 和用户聊需求并创建。
2. STATE 和代码对不上时，以代码和测试为准，并修正 STATE。
3. 有明显没被 STATE 记录的改动（未提交的 diff、STATE 之后的 commit）时，用 continuity skill 的 recover 补全。
4. 动手前用 3～5 行告诉用户：做到哪、哪项做了一半、准备从哪继续。
**干活时**
5. 每完成 STATE 任务清单里的一项：勾掉它 → 小步 git commit。
6. 做出重要决定（选型、架构、放弃某方案）时，立刻写进 STATE 的「有效决定」，附原因。
7. 开始一项任务前，把它标成进行中 [~]，写一句打算怎么做。
8. 项目里有 DESIGN.md 时，改界面前先读它，沿用已有风格，不自创新风格。
**保持精简**
9. STATE 只记 git 查不到的：意图、决定和原因、坑、下一步。不贴代码，不记过程。
10. STATE 超过 80 行就压缩：已完成的项合并成一行；长期有效的坑先搬进 SPEC 的「约束」，再从 STATE 删掉。
<!-- cross-agent-dev:end -->
