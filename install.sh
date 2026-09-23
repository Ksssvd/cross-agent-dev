#!/usr/bin/env bash
# 把跨 Agent 接力规则和 continuity skill 装进一个项目。
#
#   ./install.sh --global                                      全局安装（推荐）
#   ./install.sh <项目目录> [--tools claude,opencode,factory]   只装进一个项目
#
# --global：把 skill 软链接到 ~/.claude/skills 和 ~/.agents/skills，所有项目可用。
#
# 装进项目时做的事（可重复运行，只改自己管理的部分）：
#   1. 复制 skill 到 <项目>/.agents/skills/continuity   （Codex 等读这里）
#   2. 为其他工具建软链接：.claude/skills、.opencode/skills、.factory/skills
#   3. 在 AGENTS.md 里追加/更新接力规则（标记之间的内容）
#   4. 确保 CLAUDE.md 里有一行 @AGENTS.md（Claude Code 通过它读规则）
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_SRC="$SRC_DIR/skill/continuity"
BLOCK="$SKILL_SRC/AGENTS.block.md"
START="<!-- cross-agent-dev:start -->"
END="<!-- cross-agent-dev:end -->"

TARGET=""
TOOLS="claude"
GLOBAL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --global) GLOBAL=1; shift ;;
    --tools) TOOLS="$2"; shift 2 ;;
    --tools=*) TOOLS="${1#*=}"; shift ;;
    -h|--help) sed -n '2,14p' "$0"; exit 0 ;;
    *) TARGET="$1"; shift ;;
  esac
done

if [[ "$GLOBAL" == 1 ]]; then
  for dir in "$HOME/.claude/skills" "$HOME/.agents/skills"; do
    link="$dir/continuity"
    mkdir -p "$dir"
    if [[ -L "$link" && "$(readlink "$link")" == "$SKILL_SRC" ]]; then
      echo "· $link 已是最新"
    elif [[ -e "$link" || -L "$link" ]]; then
      echo "! $link 已存在且指向别处，跳过（请手动处理）" >&2
    else
      ln -s "$SKILL_SRC" "$link"
      echo "✓ $link → $SKILL_SRC"
    fi
  done
  cat <<'MSG'

装好了。最后一步：把下面这行加进你的全局规则文件
（Codex：~/.codex/AGENTS.md；Claude Code：~/.claude/CLAUDE.md），两个都用就都加：

- 开始开发一个需要多次迭代的项目时，若项目里没有 SPEC.md 和 STATE.md，先用 continuity skill 建档；一次性的小任务不用。

注意：skill 是软链接，请不要移动或删除这个 cross-agent-dev 文件夹。
MSG
  exit 0
fi

if [[ -z "$TARGET" || ! -d "$TARGET" ]]; then
  echo "用法：./install.sh --global  或  ./install.sh <项目目录> [--tools claude,opencode,factory]" >&2
  exit 1
fi
TARGET="$(cd "$TARGET" && pwd)"
if [[ "$TARGET" == "$SRC_DIR" ]]; then
  echo "目标目录不能是 cross-agent-dev 自己。" >&2
  exit 1
fi

# 1. skill 本体
mkdir -p "$TARGET/.agents/skills"
rm -rf "$TARGET/.agents/skills/continuity"
cp -R "$SKILL_SRC" "$TARGET/.agents/skills/continuity"
echo "✓ skill → .agents/skills/continuity"

# 2. 其他工具的软链接
IFS=',' read -ra TOOL_LIST <<< "$TOOLS"
for tool in "${TOOL_LIST[@]}"; do
  case "$tool" in
    claude|opencode|factory) ;;
    codex|"") continue ;;  # Codex 直接读 .agents/skills
    *) echo "! 不认识的工具：$tool（可选 claude、opencode、factory）" >&2; continue ;;
  esac
  dir="$TARGET/.$tool/skills"
  link="$dir/continuity"
  mkdir -p "$dir"
  if [[ -e "$link" && ! -L "$link" ]]; then
    echo "! $link 已存在且不是软链接，跳过（请手动处理）" >&2
    continue
  fi
  ln -sfn "../../.agents/skills/continuity" "$link"
  echo "✓ .$tool/skills/continuity → .agents/skills/continuity"
done

# 3. AGENTS.md 规则块
AGENTS="$TARGET/AGENTS.md"
if [[ -L "$AGENTS" ]]; then
  echo "! AGENTS.md 是软链接，为避免改到别处，跳过。请手动把 $BLOCK 的内容加进去。" >&2
elif [[ -f "$AGENTS" ]] && grep -qF "$START" "$AGENTS"; then
  if ! grep -qF "$END" "$AGENTS"; then
    echo "! AGENTS.md 里有开始标记但没有结束标记，为避免误删内容，跳过。请手动修复。" >&2
    exit 1
  fi
  tmp="$(mktemp)"
  awk -v start="$START" -v end="$END" -v block="$BLOCK" '
    $0 == start { while ((getline line < block) > 0) print line; skip = 1; next }
    $0 == end   { skip = 0; next }
    !skip       { print }
  ' "$AGENTS" > "$tmp"
  mv "$tmp" "$AGENTS"
  echo "✓ AGENTS.md 规则已更新"
else
  if [[ -s "$AGENTS" ]]; then printf '\n' >> "$AGENTS"; fi
  cat "$BLOCK" >> "$AGENTS"
  echo "✓ AGENTS.md 已加入接力规则"
fi

# 4. CLAUDE.md 引用 AGENTS.md
if [[ " ${TOOL_LIST[*]} " == *" claude "* ]]; then
  CLAUDE_MD="$TARGET/CLAUDE.md"
  if [[ -L "$CLAUDE_MD" ]]; then
    echo "· CLAUDE.md 是软链接，跳过（通常已指向 AGENTS.md）"
  elif [[ -f "$CLAUDE_MD" ]] && grep -qxF "@AGENTS.md" "$CLAUDE_MD"; then
    echo "· CLAUDE.md 已引用 AGENTS.md"
  else
    if [[ -s "$CLAUDE_MD" ]]; then printf '\n' >> "$CLAUDE_MD"; fi
    printf '@AGENTS.md\n' >> "$CLAUDE_MD"
    echo "✓ CLAUDE.md 已加入 @AGENTS.md"
  fi
fi

if ! git -C "$TARGET" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "! 这个目录还不是 git 仓库。接力依赖 git 记录进度，建议先运行：git -C \"$TARGET\" init" >&2
fi

cat <<EOF

装好了。接下来：
  · 新项目：打开任意 Coding Agent，正常说你要做什么，它会自动建 SPEC.md 和 STATE.md。
  · 换 Agent 前：说"我要换 Agent 了，先存个档"。
  · 换过去后：说"继续这个项目"。
EOF
