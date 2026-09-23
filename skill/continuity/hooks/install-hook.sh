#!/usr/bin/env bash
# 把 STATE 提交检查装进一个 git 项目：install-hook.sh [项目目录]
# 可重复运行。不会覆盖你自己的 pre-commit，也不碰 husky 等自定义 hooks 目录。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARK="cross-agent-dev:state-check"
cd "${1:-.}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "· 不是 git 仓库，跳过提交检查"
  exit 0
fi

if [[ -n "$(git config --get core.hooksPath || true)" ]]; then
  echo "! 项目用了自定义 hooks 目录（core.hooksPath），没有自动安装提交检查。" >&2
  echo "  如需要，请在你的 pre-commit 里调用：$HERE/pre-commit" >&2
  exit 0
fi

hook="$(git rev-parse --git-path hooks)/pre-commit"
mkdir -p "$(dirname "$hook")"
if [[ -e "$hook" ]] && ! grep -qF "$MARK" "$hook"; then
  echo "! 已有别的 pre-commit，没有覆盖。如需要，请在里面调用：$HERE/pre-commit" >&2
  exit 0
fi

cp "$HERE/pre-commit" "$hook"
chmod +x "$hook"
echo "✓ STATE 提交检查已安装"
