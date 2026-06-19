# 安装

> 「一句话/一条命令就装好、还不用事先拿到包」的前提是：**包先托管在 Agent 够得到的公开位置**（GitHub）。
> 下面前两种是托管后的真·一键（仓库 `wailii/universal-tutor`，需先推到公开 GitHub）；第三种是离线自带包。

## 方式 A：一条命令（curl，跨任意带 shell 的 Agent / 自己跑）

```bash
curl -fsSL https://raw.githubusercontent.com/wailii/universal-tutor/main/install.sh | bash
```

自动探测 skills 目录（Claude Code `~/.claude/skills/`、Codex `~/.codex/skills/`，否则当前目录）→ git clone/下载 → init → boot 自检。指定目录加 `INSTALL_DIR=/路径`。

## 方式 B：Claude Code 原生插件（/plugin）

仓库已带 `.claude-plugin/{plugin.json,marketplace.json}`，推到公开 GitHub 后：

```
/plugin marketplace add wailii/universal-tutor
/plugin install universal-tutor@universal-tutor-mkt
```

## 方式 C：一句提示词（发给任意 Agent，无需你手动敲命令）

```
帮我安装 universal-tutor 学习 skill：把 https://github.com/wailii/universal-tutor
clone 到我的 skills 目录（Claude Code 用 ~/.claude/skills/，Codex 用 ~/.codex/skills/），
然后 cd 进去跑 python3 scripts/tutor.py init && boot 确认能用，
装好后告诉我有哪些内置课、怎么开始学、怎么让你给我现场新建一门课。
```

## 方式 D：离线（没有 GitHub，自带包）

用我单独给的自解压安装器（整个 skill 用 base64 内嵌，单文件即可）：

```bash
bash universal-tutor-offline-installer.sh
```

---

## 关于可写性（重要）

`tutor.py` 默认把 `state/`、`logs/`、新建的 `packs/` 写在安装目录附近。

- **方式 A / C / D**（装进 `~/.claude/skills/` 等可写目录）：开箱即用，无需额外设置。
- **方式 B（/plugin）**：插件会被拷进只读的 `~/.claude/plugins/cache/`，直接写会失败。请把可变数据重定向到可写工作区，并把内置课一并放过去：
  ```bash
  mkdir -p ~/.universal-tutor && cp -r <插件目录>/packs ~/.universal-tutor/   # 首次
  export TUTOR_PACKS_DIR=~/.universal-tutor/packs
  export TUTOR_STATE_DIR=~/.universal-tutor/state
  export TUTOR_LOG_DIR=~/.universal-tutor/logs
  ```
  （或干脆用方式 A 装进可写 skills 目录，省掉这一步。）

唯一硬依赖：**Python 3**（标准库即可）。业界对标环节需 Agent 能联网，不能联网会自动降级并如实标注。
