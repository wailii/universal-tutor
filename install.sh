#!/usr/bin/env bash
# universal-tutor 在线安装器 —— 从 GitHub 拉取并装进你的 skills 目录。用户无需事先持有任何包。
#
#   一条命令（推荐）：
#     curl -fsSL https://raw.githubusercontent.com/<OWNER>/universal-tutor/main/install.sh | bash
#
#   指定装到哪：   INSTALL_DIR=/你的/skills目录 bash <(curl -fsSL .../install.sh)
#   换仓库/分支：  UT_REPO=https://github.com/you/universal-tutor UT_BRANCH=main bash install.sh
#
# ⚠️ 把上面的 <OWNER> 改成你的 GitHub 用户名后再用（推到公开仓库才可达）。
set -e
REPO="${UT_REPO:-https://github.com/<OWNER>/universal-tutor}"
BRANCH="${UT_BRANCH:-main}"

if [ -n "${INSTALL_DIR:-}" ]; then
  DEST="$INSTALL_DIR"
elif [ -d "$HOME/.claude" ]; then
  DEST="$HOME/.claude/skills/universal-tutor"
elif [ -d "$HOME/.codex" ]; then
  DEST="$HOME/.codex/skills/universal-tutor"
else
  DEST="$PWD/universal-tutor"
fi
command -v python3 >/dev/null 2>&1 || { echo "✗ 需要 python3，请先安装。"; exit 1; }
echo "[universal-tutor] 安装到 $DEST  （来源 $REPO@$BRANCH）"

if command -v git >/dev/null 2>&1; then
  if [ -d "$DEST/.git" ]; then
    git -C "$DEST" pull --ff-only || true
  else
    rm -rf "$DEST"
    git clone --depth 1 -b "$BRANCH" "$REPO" "$DEST"
  fi
elif command -v curl >/dev/null 2>&1; then
  mkdir -p "$DEST"
  curl -fsSL "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar xz --strip-components=1 -C "$DEST"
else
  echo "✗ 需要 git 或 curl 之一。"; exit 1
fi

cd "$DEST"
python3 scripts/tutor.py init >/dev/null 2>&1 || true
echo "[universal-tutor] 自检（boot）："
python3 scripts/tutor.py boot || true
cat <<EOF

✅ 装好了：$DEST
   开始：直接对你的 Agent 说「学训推平台」「考考我」「我想学 X（没有就现场建一门）」
   看内置课：cd "$DEST" && python3 scripts/tutor.py packs
EOF
