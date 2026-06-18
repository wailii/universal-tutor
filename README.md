# 通用学习导师（苏格拉底式 · 可持久化 · 热插拔多学科）

一套跑在 Claude Code / Codex / 其它 Agent 上的学习系统：用苏格拉底式提问逼你把**任何学科**想明白，目标是**能做判断、扛得住追问**——不是面试糊弄级。学习状态全程落文件，关掉再开、隔几天再来都能无缝续上。

它从一个"只会教训推平台"的专用导师，升级成**热插拔的通用导师**：装好后你选想学什么（一门或多门），没有现成课程就**现场联网建一门**；而且学习框架比专用版更扎实。

## 它为你做五件事

1. **苏格拉底引导**：不灌输，用追问把理解压回你身上；卡住时降台阶而不是给答案。提问母题拉向"判断"，不是死记。
2. **全程留痕**：每天学的实时写进 `logs/<课程>/YYYY-MM-DD.md`，跨天自动分文件、自动补当日小结。
3. **进度 + 测验 + 复习**：依赖解锁的闯关进度条；学完必须测验验证（按认知层级出题、记录置信度、连续两次达标才算掌握）；到期自动间隔+交错复习，防"进度全绿、脑子空"。
4. **专打"似懂非懂"**：置信度校准揪出"自信却错"的危险区；误概念账本把你搞混的点做成可清的闭环待办。
5. **对标真实世界**：涉及业界一律联网核实、严禁编造，逼出"谁在做、差异在哪"。

## 为什么是"热插拔多学科"

- **一个 Skill + N 张卡带**，不是装 N 个 Skill。换学科是切当前卡带（`use`），**不复制 Skill、不会触发词打架**。
- 每门课 = `packs/<id>/` 一个目录：课程图 + 学习者画像 + 对标锚点。加课不动一行引擎代码。
- 没有现成课？按 `references/pack_authoring_protocol.md` 的六步流水线**现场建一门**：澄清对话 → 联网深调研 → 生成节点图 → 对抗式自检 → 按你水平校准。

## 目录结构

```
universal-tutor/
├── SKILL.md                       # Claude Code 入口（总编排）
├── AGENTS.md                      # Codex / 其它 Agent 入口（含弱宿主强化 + 跨 agent 降级）
├── scripts/tutor.py               # 唯一状态引擎（零依赖，学科无关）
├── references/                    # 学习框架（怎么教，全部学科无关）
│   ├── learning_framework.md      #   总纲 + 背后的学习科学
│   ├── socratic_protocol.md       #   苏格拉底硬纪律（画像参数化 + ZPD 台阶）
│   ├── assessment_protocol.md     #   Bloom 分层出题 + 置信度校准 + 迁移 + 评分
│   ├── review_protocol.md         #   间隔 + 交错 + 检索式复习
│   ├── misconception_protocol.md  #   误概念账本闭环
│   ├── grounding_protocol.md      #   对标检索纪律 + 无联网降级
│   └── logging_protocol.md        #   启动校准 + 实时落盘（多包命名空间）
│   └── pack_authoring_protocol.md #   现场建一门新课的流水线
└── packs/                         # 可插拔学习卡带（每门课一个目录）
    ├── training-infra/           #   内置课①：大模型训推 + 算力调度（27 节点，每节点≥2 种子）
    │   ├── pack.json             #     元数据：学习者画像/目标/评估风格/对标开关
    │   ├── curriculum.json       #     节点图：依赖 + 目标 + Bloom + 苏格拉底种子 + 对标锚点
    │   └── grounding.md          #     本课对标锚点清单
    └── rag-systems/              #   内置课②：RAG 系统设计（53 节点，建包流水线现场生成的范例）
   （运行后自动生成：state/<课程>/ 进度与误概念、logs/<课程>/ 每日日志）
```

> `rag-systems` 是用 `pack_authoring_protocol` 的「逐节点深挖」流水线**现场生成**的：53 节点、每个 objective ~640 字、引用经联网抽样核实全部真实——既是一门可学的课，也是「生成不敷衍」的活样本。对比一次性生成同领域只得 19 个一句话节点。

## 安装

详见 `INSTALL.md`。最快的一条命令（先把 `<OWNER>` 换成你的 GitHub 用户名、推到公开仓库）：

```bash
curl -fsSL https://raw.githubusercontent.com/<OWNER>/universal-tutor/main/install.sh | bash
```

Claude Code 也可用原生插件：`/plugin marketplace add <OWNER>/universal-tutor` 再 `/plugin install universal-tutor@universal-tutor-mkt`。没有 GitHub 就用离线自解压器 `universal-tutor-offline-installer.sh`。

装好后首次：
```bash
python scripts/tutor.py packs    # 看内置课
python scripts/tutor.py init     # 初始化当前课（想重置加 --force）
python scripts/tutor.py boot     # 每次开场都跑
```

状态与日志保存在项目内 `state/` 和 `logs/`（按课程隔离）。更新脚本/协议时不要覆盖、删除这两个目录；只在明确要重开某课进度时用 `init --force --pack <id>`。

需要把状态/日志写到别处：
```bash
TUTOR_STATE_DIR=/path/state TUTOR_LOG_DIR=/path/logs TUTOR_PACKS_DIR=/path/packs python scripts/tutor.py boot
```

## 日常怎么用

直接说人话：
- 「学训推平台」「继续昨天的」「换成学 K8s 调度」「我想学 X（没有就现场建）」
- 「考考我 TRN-04」「我学到哪了」「今天复习啥」「同时也想学另一门」

它会自己 `boot` 校准、挑节点、铺最小地基、转苏格拉底、联网对标、测验评分、落盘。你只管被它问、动脑子答。

看进度 / 日志：
```bash
python scripts/tutor.py progress --all     # 所有课进度
cat logs/<课程>/YYYY-MM-DD.md              # 某天学了啥
python scripts/tutor.py miss list          # 还没补的薄弱点
```

## 几个设计取舍（知道了好改）

- **复习算法**：零依赖 SM-2 简化版（`tutor.py` 的 `schedule()`）。想换 Anki 同款 FSRS：`pip install fsrs` 后替换该函数，其余不动。
- **掌握判定**：≥4 达标，连续两次→已掌握；mastered 到期仍会被抽查。阈值改 `cmd_master`。
- **课程是单一真相源**：节点定义只在 `packs/<id>/curriculum.json` 一处（不再像原版散在代码+文档两处）。改课直接改它，引擎下次自动补齐新节点、重算解锁。
- **课程与进度分离**：`packs/` 是不可变课程，`state/` 是可变进度，互不污染。
- **日期**一律取系统时间，不接受模型传入——跨天判断不被模型瞎编的关键。
- **教学内容不预写死**：课程图只有骨架和引子，真正的讲解每次现场生成 + 联网，保证新鲜、有出处、不幻觉。
- **跨 agent**：先保 Python 宿主；无联网/无 Python 的降级路径见 `AGENTS.md` 与 `grounding_protocol.md`。
