#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tutor.py — 通用「苏格拉底式 · 可持久化」学习系统的状态引擎（唯一脚本入口）。

设计第一原则：**凡是能用脚本钉死的，绝不交给模型自觉。**
- 日期一律取系统时间（date.today），不接受模型传入 → 杜绝跨天判断被模型瞎编。
- 掌握度、解锁、复习间隔、校准统计由确定性逻辑算，不靠模型"觉得你掌握了"。
- 落盘是真写文件，不是模型口头说"已记录"。

它与原 training-infra-tutor 的关键区别（通用化 + 框架升级）：
1. **引擎与学科解耦**：课程内容不再硬编码在本文件，而是从 packs/<id>/curriculum.json 读。
   本脚本对任何学科一视同仁。加学科 = 加一个包目录，不动代码。
2. **课程(不可变) 与 进度(可变) 分离**：
   - packs/<id>/curriculum.json  → 课程骨架（节点/依赖/目标/Bloom 层级/苏格拉底种子/对标锚点）
   - state/<id>/progress.json     → 学习者状态（状态机/连续达标/复习排期/校准历史）
   原版把标题塞进 progress.json、课程塞进 .py，改课要两处对齐；现在课程是单一真相源。
3. **多包热插拔**：可同时安装多张"卡带"，state 和 logs 按包命名空间隔离；
   boot 跨所有已装包汇总到期复习（交错复习的地基）。
4. **评估升级（让"掌握"更立得住）**：
   - Bloom/认知层级写进每个节点 → 测验按层级出题，掌握判定不一刀切。
   - 置信度校准：master 时可记录用户自报置信度，引擎自动统计"自信却错"的危险区。
   - 误概念账本：结构化（JSON）闭环——open/retired + 复测次数，复习优先打开放项。
   - 掌握仍是"连续两次 ≥4 才升 mastered"，且复习到期会把 mastered 拉回来抽查。

教学内容（怎么讲、怎么追问、怎么对标）不在本脚本——见 references/ 协议。
脚本只管骨架、状态、解锁、复习、校准、留痕。
"""
import argparse
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 路径可被环境变量覆盖（便于跨 agent / 沙箱里改写到别处）。
PACKS_DIR = os.environ.get("TUTOR_PACKS_DIR", os.path.join(ROOT, "packs"))
STATE_ROOT = os.environ.get("TUTOR_STATE_DIR", os.path.join(ROOT, "state"))
LOG_ROOT = os.environ.get("TUTOR_LOG_DIR", os.path.join(ROOT, "logs"))
ACTIVE_FILE = os.path.join(STATE_ROOT, "active.json")

DONE = {"learned", "mastered"}          # 视为"已通过、可解锁后继"的状态
BLOOM_LEVELS = ["understand", "apply", "analyze", "evaluate", "create"]
CONF_LEVELS = ["low", "med", "high"]
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")   # 合法包名/节点名
_CORRUPT = object()                                      # read_json 解析失败哨兵


# ============================ 通用小工具 ============================
def today_str():
    return date.today().isoformat()


def die(msg):
    sys.exit(msg)


def check_pack_id(pid):
    """挡掉路径穿越和非法包名（../、/、空格、奇怪字符）。"""
    if not pid or not SAFE_ID.match(pid) or ".." in pid or "/" in pid or "\\" in pid:
        die(f"非法包名：{pid!r}（只允许字母/数字/点/下划线/连字符，且不含 .. 和路径分隔符）")
    return pid


def read_json(path, default=None):
    """读 JSON。文件不存在→default；存在但损坏→_CORRUPT（由调用方决定 die 还是跳过）。"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return _CORRUPT


def write_json(path, data):
    # 原子写：先写临时文件再 os.replace，杜绝写到一半被打断留下损坏/截断的 JSON。
    # （注：仍假设单写者；并发多写者需外部加锁，本系统按单 agent 使用。）
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ============================ 包(pack)解析 ============================
def list_installed():
    """已安装的包 = packs/ 下含 curriculum.json 的子目录。"""
    out = []
    if not os.path.isdir(PACKS_DIR):
        return out
    for name in sorted(os.listdir(PACKS_DIR)):
        d = os.path.join(PACKS_DIR, name)
        if os.path.isdir(d) and os.path.exists(os.path.join(d, "curriculum.json")):
            out.append(name)
    return out


def load_active_meta():
    meta = read_json(ACTIVE_FILE, default=None)
    if not isinstance(meta, dict):          # 缺失或损坏 → 重建
        meta = None
    installed = list_installed()
    if meta is None:
        meta = {"current": (installed[0] if installed else None), "installed": installed}
    meta["installed"] = installed  # 永远以磁盘为准
    if meta.get("current") not in installed:
        meta["current"] = installed[0] if installed else None
    return meta


def save_active_meta(meta):
    write_json(ACTIVE_FILE, meta)


def resolve_pack(explicit=None):
    """优先级：命令行 --pack > 环境变量 TUTOR_PACK > active.json current。"""
    pid = explicit or os.environ.get("TUTOR_PACK") or load_active_meta().get("current")
    if not pid:
        die("还没有安装任何学习包。先建包：python scripts/tutor.py new-pack <id> '<标题>'，"
            "或参考 references/pack_authoring_protocol.md 现场生成一个。")
    if pid not in list_installed():
        die(f"未安装的包：{pid}。已装：{', '.join(list_installed()) or '（无）'}")
    return pid


def pack_dir(pid):
    return os.path.join(PACKS_DIR, pid)


def load_curriculum(pid):
    path = os.path.join(pack_dir(pid), "curriculum.json")
    cur = read_json(path)
    if cur is _CORRUPT:
        die(f"包 {pid} 的 curriculum.json 是损坏的 JSON，无法解析：{path}\n  修复它，或重新建包。")
    if not cur or "nodes" not in cur:
        die(f"包 {pid} 的 curriculum.json 缺失或无 nodes 字段。")
    return cur


def peek_curriculum(pid):
    """跨包只读窥视：缺失/损坏/无效都返回 None（不 die），用于汇总场景跳过坏包。"""
    d = read_json(os.path.join(pack_dir(pid), "curriculum.json"))
    if d is None or d is _CORRUPT or not isinstance(d, dict) or "nodes" not in d:
        return None
    return d


def peek_progress(pid):
    d = read_json(progress_path(pid))
    return None if (d is None or d is _CORRUPT or not isinstance(d, dict)) else d


def validate_curriculum(cur):
    """返回 [(severity, msg)]，severity ∈ {'error','warn'}。空 = 完全健康。
    error = 结构性（会卡死解锁/越界/崩判定），必须修；warn = 质量问题（空目标/空种子），建议修。
    建包质量护栏的核心——比旧版多查 bloom 合法性与节点语义质量。"""
    out = []
    nodes = cur.get("nodes", [])
    if not isinstance(nodes, list):
        return [("error", "nodes 不是数组")]
    ids = [n.get("id") for n in nodes]
    for i, n in enumerate(nodes):
        nid = n.get("id")
        if not nid:
            out.append(("error", f"第 {i + 1} 个节点缺 id"))
        elif not SAFE_ID.match(str(nid)):
            out.append(("error", f"节点 id 含非法字符：{nid!r}"))
        if not n.get("title"):
            out.append(("error", f"节点 {nid or '?'} 缺 title"))
        b = n.get("bloom")
        if b is not None and b not in BLOOM_LEVELS:
            out.append(("error", f"节点 {nid} 的 bloom 非法：{b!r}（须是 {BLOOM_LEVELS} 之一）"))
        obj = (n.get("objective") or "").strip()
        if not obj:
            out.append(("warn", f"节点 {nid} 的 objective 为空（学到什么程度说不清，测验无从验收）"))
        elif len(obj) < 25:
            out.append(("warn", f"节点 {nid} 的 objective 过短（{len(obj)}字，疑似敷衍/占位）"))
        seeds = n.get("socratic_seeds") or []
        if len(seeds) < 2:
            out.append(("warn", f"节点 {nid} 的 socratic_seeds 只有 {len(seeds)} 个（建议≥2，连环追问才够用）"))
    seen, dups = set(), set()
    for nid in ids:
        if nid in seen:
            dups.add(nid)
        seen.add(nid)
    for d in sorted(x for x in dups if x):
        out.append(("error", f"重复的节点 id：{d}"))
    idset = set(i for i in ids if i)
    for n in nodes:
        for d in (n.get("deps") or []):
            if d not in idset:
                out.append(("error", f"节点 {n.get('id')} 依赖了不存在的节点：{d}"))
    # 环检测（deps 是先修关系；成环则永远解锁不了）
    graph = {n.get("id"): [d for d in (n.get("deps") or []) if d in idset]
             for n in nodes if n.get("id")}
    color = {k: 0 for k in graph}   # 0 白 1 灰 2 黑
    cycles = []

    def dfs(u, stack):
        color[u] = 1
        for v in graph.get(u, []):
            if color.get(v) == 1:
                cycles.append(" → ".join(stack + [u, v]))
            elif color.get(v) == 0:
                dfs(v, stack + [u])
        color[u] = 2

    for k in list(graph):
        if color[k] == 0:
            dfs(k, [])
    for c in cycles[:5]:
        out.append(("error", f"依赖成环：{c}"))
    return out


def curriculum_errors(cur):
    """仅返回结构性 error 的消息列表（用于把 validate 当闸门）。"""
    return [m for sev, m in validate_curriculum(cur) if sev == "error"]


def load_pack_meta(pid):
    return read_json(os.path.join(pack_dir(pid), "pack.json"), default={"id": pid, "title": pid})


def state_dir(pid):
    return os.path.join(STATE_ROOT, pid)


def progress_path(pid):
    return os.path.join(state_dir(pid), "progress.json")


def misconceptions_path(pid):
    return os.path.join(state_dir(pid), "misconceptions.json")


def log_dir(pid):
    return os.path.join(LOG_ROOT, pid)


# ============================ 进度(state)装载 ============================
def fresh_node_state(nid):
    return {
        "id": nid,
        "status": "locked",
        "streak": 0,
        "last_score": None,
        "bloom_reached": None,        # 测验里达到过的最高 Bloom 层级
        "confidence_log": [],         # [{date, score, confidence}] → 校准
        "sm2": {"ease": 2.5, "interval_days": 0, "reps": 0},
        "last_reviewed": None,
        "next_review": None,
        "last_streak_date": None,     # 上一次"计入掌握的达标"是哪天 → 掌握需跨天
        "title_seen": None,           # 记录课程里该节点标题，变了说明 id 内容被换 → 旧掌握作废
        "history": [],
    }


def load_progress(pid, create=True):
    """默认 create=True：缺进度就自动初始化（杜绝"开场 boot 必崩"）。同时做活课程对齐、
    字段补全（防半迁移崩栈）、旧单槽 pending 迁移成列表、id 内容指纹校验。"""
    p = read_json(progress_path(pid), default=None)
    if p is _CORRUPT:
        die(f"包 {pid} 的 progress.json 损坏。用 `python scripts/tutor.py init --force --pack {pid}` "
            f"重建（会清空该课进度），或手工修复该 JSON。")
    cur = load_curriculum(pid)
    cur_ids = [n["id"] for n in cur["nodes"]]
    if p is None:
        if not create:
            die(f"包 {pid} 尚未初始化进度。先跑：python scripts/tutor.py init --pack {pid}")
        p = {"version": "2.1", "pack": pid, "created": today_str(),
             "last_active_date": None, "pending_summaries": [],
             "current_focus": None, "nodes": {}}
    p.setdefault("nodes", {})
    # 迁移：旧的单槽 pending_summary_date → 列表 pending_summaries（防多天断更丢小结）
    p.setdefault("pending_summaries", [])
    old_pending = p.pop("pending_summary_date", None)
    if old_pending and old_pending not in p["pending_summaries"]:
        p["pending_summaries"].append(old_pending)
    p["version"] = "2.1"
    # 活课程对齐：补齐缺节点；给已存在但字段残缺的节点补全字段（防旧 state 半迁移后崩栈）
    ref = fresh_node_state("X")
    titles = {n["id"]: n.get("title", "") for n in cur["nodes"]}
    today = today_str()
    for nid in cur_ids:
        st = p["nodes"].get(nid)
        if st is None:
            p["nodes"][nid] = fresh_node_state(nid)
            st = p["nodes"][nid]
        else:
            for k, v in ref.items():
                if k == "id":
                    continue
                if isinstance(v, list):
                    st.setdefault(k, [])
                elif isinstance(v, dict):
                    st.setdefault(k, dict(v))
                else:
                    st.setdefault(k, v)
            for k, v in ref["sm2"].items():
                st["sm2"].setdefault(k, v)
        # id 内容指纹：标题变了且曾达标 → 说明这个 id 被换了内容，旧掌握作废、需重验
        seen = st.get("title_seen")
        nowt = titles.get(nid, "")
        if seen is None:
            st["title_seen"] = nowt
        elif seen != nowt and st.get("status") in ("learned", "mastered"):
            st["status"] = "learning"
            st["streak"] = 0
            st["last_streak_date"] = None
            st["title_seen"] = nowt
            st.setdefault("history", []).append(
                {"date": today, "event": "content_changed", "score": None})
    return p, cur


def touch_active(pid, p, today):
    """记录一次"真实学习活动"。若跨天，把上一个【确实有学习日志】的活跃日排进待补小结队列，
    然后把活跃日推进到今天。修复：①只有 boot 抓跨天 ②单槽丢小结 ③不补就永久 nag+状态矛盾。"""
    p.setdefault("pending_summaries", [])
    prev = p.get("last_active_date")
    if prev and prev != today and prev not in p["pending_summaries"]:
        if os.path.exists(os.path.join(log_dir(pid), f"{prev}.md")):  # 没学过的空白天不补
            p["pending_summaries"].append(prev)
    p["last_active_date"] = today
    return p["pending_summaries"]


def save_progress(pid, p):
    write_json(progress_path(pid), p)


def cur_map(cur):
    return {n["id"]: n for n in cur["nodes"]}


def refresh_locks(p, cur):
    """重算 locked/available：deps 全部 learned/mastered 才解锁。已在学/学过的不回退。"""
    cm = cur_map(cur)
    st = p["nodes"]
    for nid, node in cm.items():
        s = st[nid]
        if s["status"] in ("learning", "learned", "mastered"):
            continue
        deps = node.get("deps", [])
        deps_ok = all(st.get(d, {}).get("status") in DONE for d in deps)
        s["status"] = "available" if deps_ok else "locked"


# ============================ SM-2 复习排期 ============================
# 零依赖简化版。想升级到 Anki 同款 FSRS：pip install fsrs，替换本函数即可，
# 其余调用方（master/review/boot）无需改动。
def schedule(node_state, score, when):
    sm = node_state["sm2"]
    if score >= 4:
        if sm["reps"] == 0:
            sm["interval_days"] = 1
        elif sm["reps"] == 1:
            sm["interval_days"] = 3
        else:
            sm["interval_days"] = max(1, round(sm["interval_days"] * sm["ease"]))
        sm["reps"] += 1
        sm["ease"] = min(3.0, max(1.3, sm["ease"] + (0.1 - (5 - score) * (0.08 + (5 - score) * 0.02))))
    else:
        sm["reps"] = 0
        sm["interval_days"] = 1
        sm["ease"] = max(1.3, sm["ease"] - 0.2)
    nxt = datetime.strptime(when, "%Y-%m-%d").date() + timedelta(days=sm["interval_days"])
    node_state["last_reviewed"] = when
    node_state["next_review"] = nxt.isoformat()


# ============================ 校准统计 ============================
def calibration_flags(p):
    """返回 (overconfident, underconfident) 节点列表 —— 治"似懂非懂/盲目自信"。
    只看每个节点【最近一次】带置信度的测验：一旦后来校准好了就自动退出危险区（召回窗口），
    不再像旧版那样一旦命中就永久挂牌。"""
    over, under = [], []
    for nid, s in p["nodes"].items():
        log = s.get("confidence_log", [])
        if not log:
            continue
        e = log[-1]
        if e.get("confidence") == "high" and e.get("score", 5) < 4:
            over.append(nid)
        elif e.get("confidence") == "low" and e.get("score", 0) >= 4:
            under.append(nid)
    return sorted(set(over)), sorted(set(under))


# ============================ 误概念账本 ============================
def load_miscon(pid):
    d = read_json(misconceptions_path(pid), default=None)
    if not isinstance(d, dict) or "items" not in d:   # 缺失或损坏 → 空账本
        d = {"pack": pid, "items": []}
    return d


def save_miscon(pid, data):
    write_json(misconceptions_path(pid), data)


# ============================ 子命令 ============================
def cmd_new_pack(args):
    pid = check_pack_id(args.id)
    d = pack_dir(pid)
    if os.path.exists(os.path.join(d, "curriculum.json")) and not args.force:
        die(f"包已存在：{d}（覆盖加 --force）")
    os.makedirs(d, exist_ok=True)
    meta = {
        "id": pid,
        "title": args.title or pid,
        "description": "",
        "learner_profile": "（建包时由 pack_authoring 流程写入：学习者是谁、背景、目标）",
        "goal": "",
        "target_depth": "",
        "assessment_styles": ["concept", "drill", "transfer", "scenario"],
        "socratic_orientation": "（提问母题拉向什么判断，由建包流程定）",
        "grounding": True,
        "created": today_str(),
    }
    write_json(os.path.join(d, "pack.json"), meta)
    write_json(os.path.join(d, "curriculum.json"),
               {"pack": pid, "nodes": []})
    with open(os.path.join(d, "grounding.md"), "w", encoding="utf-8") as f:
        f.write(f"# 对标锚点 · {meta['title']}\n\n（建包流程联网调研后填入本学科的对标对象清单）\n")
    print(f"已创建空包骨架 → {d}")
    print("下一步：按 references/pack_authoring_protocol.md 把 curriculum.json 的 nodes 填满，再 init。")


def cmd_install(args):
    """把某个已存在的包设为已装并切为当前（packs/ 下放进目录即视为已装；本命令只切 current）。"""
    pid = args.id
    if pid not in list_installed():
        die(f"packs/ 下没有包 {pid}。")
    meta = load_active_meta()
    meta["current"] = pid
    save_active_meta(meta)
    print(f"当前学习包 → {pid}")


def cmd_use(args):
    pid = args.id
    if pid not in list_installed():
        die(f"未安装：{pid}。已装：{', '.join(list_installed()) or '（无）'}")
    meta = load_active_meta()
    meta["current"] = pid
    save_active_meta(meta)
    pm = load_pack_meta(pid)
    print(f"已切到学习包：{pid}  「{pm.get('title', pid)}」")


def cmd_packs(args):
    installed = list_installed()
    meta = load_active_meta()
    if not installed:
        print("还没有安装任何学习包。建一个：python scripts/tutor.py new-pack <id> '<标题>'")
        return
    print("已安装的学习包：")
    for pid in installed:
        pm = load_pack_meta(pid)
        mark = "▶" if pid == meta.get("current") else " "
        p = peek_progress(pid)
        cur = peek_curriculum(pid)
        if cur is None:
            prog = "课程文件损坏/缺失"
        elif p:
            total = len(cur["nodes"])
            mastered = sum(1 for s in p.get("nodes", {}).values() if s.get("status") == "mastered")
            prog = f"{mastered}/{total} 已掌握"
        else:
            prog = "未初始化"
        print(f"  {mark} {pid:22s} {pm.get('title', pid)}  [{prog}]")


def cmd_init(args):
    pid = resolve_pack(args.pack)
    if os.path.exists(progress_path(pid)) and not args.force:
        print(f"已存在进度，未覆盖（重置加 --force）：{progress_path(pid)}")
        return
    cur = load_curriculum(pid)
    # validate 当闸门：结构性 error 会卡死解锁，默认拒绝 init（除非 --force 明确放行）
    errs = curriculum_errors(cur)
    if errs and not args.force:
        print(f"✗ 包 {pid} 的课程有 {len(errs)} 个结构性问题，已拒绝初始化（修好，或 --force 强行）：")
        for x in errs:
            print(f"   - {x}")
        print(f"   跑 `python scripts/tutor.py validate --pack {pid}` 看全部。")
        sys.exit(1)
    if os.path.exists(progress_path(pid)) and args.force:
        os.remove(progress_path(pid))
    p, cur = load_progress(pid, create=True)
    refresh_locks(p, cur)
    save_progress(pid, p)
    meta = load_active_meta()
    meta["current"] = pid
    save_active_meta(meta)
    print(f"包 {pid} 已初始化 {len(cur['nodes'])} 个知识节点 → {progress_path(pid)}")
    warns = [m for sev, m in validate_curriculum(cur) if sev == "warn"]
    if errs:
        print(f"⚠️ （--force 放行了 {len(errs)} 个结构性问题，节点可能解锁不了，记得修）")
    if warns:
        print(f"⚠️ {len(warns)} 个质量问题（不挡 init，但建议补）：")
        for x in warns[:4]:
            print(f"   - {x}")


def _due_nodes(p, cur, today):
    """到期复习：已达标(learned/mastered)且 next_review 到期。"""
    cm = cur_map(cur)
    return [nid for nid, s in p["nodes"].items()
            if nid in cm and s.get("next_review") and s["next_review"] <= today
            and s["status"] in DONE]


def _relearn_due(p, cur, today):
    """需重学：上次没达标(learning)、排了重练日且已到。修复"失败节点排了复习却永不提示"。"""
    cm = cur_map(cur)
    return [nid for nid, s in p["nodes"].items()
            if nid in cm and s.get("next_review") and s["next_review"] <= today
            and s["status"] == "learning"]


def cmd_boot(args):
    pid = resolve_pack(args.pack)
    first = not os.path.exists(progress_path(pid))   # 首次：load_progress 会自动初始化
    p, cur = load_progress(pid)                       # create=True → 不会再"开场即崩"
    cm = cur_map(cur)
    refresh_locks(p, cur)
    today = today_str()
    pm = load_pack_meta(pid)

    prev = p.get("last_active_date")
    pending = touch_active(pid, p, today)             # 跨天结算（多天断更也不丢）

    print("=== 启动校准 ===")
    print(f"当前学习包：{pid}  「{pm.get('title', pid)}」")
    print(f"今天：{today}    上次活跃：{prev or '（首次）'}")
    if first:
        print(f"（首次：已自动初始化 {len(cur['nodes'])} 个节点）")
    probs = validate_curriculum(cur)
    if probs:
        ne = sum(1 for sev, _ in probs if sev == "error")
        print(f"⚠️ 课程有 {len(probs)} 个问题（其中 {ne} 个结构性，会卡住解锁）→ "
              f"`validate --pack {pid}` 查看")
    if not cur["nodes"]:
        print("\n这门课还没有任何节点。按 references/pack_authoring_protocol.md 把 curriculum.json 填上"
              "（或让我现场帮你建），再来 boot。")
    if pending:
        print("\n⚠️ 有未补的当日小结（不补会一直提醒；不想补就放弃）：")
        for dte in pending:
            print(f"   · {dte}：补 → `echo '小结' | python scripts/tutor.py log __DAILY_SUMMARY__`"
                  f"    放弃 → `python scripts/tutor.py skip-summary {dte}`")

    # 本包到期复习
    due = _due_nodes(p, cur, today)
    if due:
        print("\n本包到期复习（先清这些再学新的，直接上连环追问，不是重念）：")
        for nid in due:
            s = p["nodes"][nid]
            print(f"  · {nid} {cm[nid]['title']}  (上次 {s['last_score']} 分，应复习于 {s['next_review']})")
    else:
        print("\n本包到期复习：无")

    # 需重学（上次没达标、到重练日）
    relearn = _relearn_due(p, cur, today)
    if relearn:
        print("\n需重学（上次没达标、已到重练日，重学并重测）：")
        for nid in relearn:
            s = p["nodes"][nid]
            print(f"  · {nid} {cm[nid]['title']}  (上次 {s['last_score']} 分，应重练于 {s['next_review']})")

    # 跨包到期复习（交错复习的提示；不强制，但提醒别只盯一门）
    other_due = []
    for opid in list_installed():
        if opid == pid:
            continue
        op = peek_progress(opid)
        ocur = peek_curriculum(opid)
        if not op or not ocur:
            continue
        od = _due_nodes(op, ocur, today)
        if od:
            other_due.append((opid, len(od)))
    if other_due:
        s = "，".join(f"{opid}:{n}个" for opid, n in other_due)
        print(f"\n其它包也有到期复习（可交错复习提升迁移）：{s}")

    # 开放误概念（优先打）
    mis = load_miscon(pid)
    open_mis = [m for m in mis["items"] if m.get("status") == "open"]
    if open_mis:
        print(f"\n开放的误概念 {len(open_mis)} 条（复习时优先复测、纠正）：")
        for m in open_mis[:6]:
            print(f"  · [{m['id']}] ({m.get('node','-')}) {m['text']}")
        if len(open_mis) > 6:
            print(f"  …… 共 {len(open_mis)} 条，`tutor.py miss list` 看全")

    # 校准危险区
    over, under = calibration_flags(p)
    if over:
        print(f"\n⚠️ 自信却答错的危险区（重点复测）：{', '.join(over)}")

    # 可学 + focus + 进度
    print(f"\n当前 focus：{p.get('current_focus') or '（未设定）'}")
    avail = [nid for nid, s in p["nodes"].items() if s["status"] == "available" and nid in cm]
    print("可学节点（依赖已满足）：")
    for nid in avail[:8]:
        print(f"  · {nid} {cm[nid]['title']}")
    if len(avail) > 8:
        print(f"  …… 共 {len(avail)} 个")
    print()
    _print_progress(pid, p, cur, brief=True)

    # last_active_date 已由 touch_active 推进；这里只落盘
    save_progress(pid, p)


def cmd_log(args):
    pid = resolve_pack(args.pack)
    body = sys.stdin.read().strip()
    if not body:
        die("log 需要从 stdin 传入正文。用法：echo '内容' | tutor.py log TRN-01")
    p, cur = load_progress(pid)
    cm = cur_map(cur)
    today = today_str()
    p.setdefault("pending_summaries", [])
    is_summary = (args.node == "__DAILY_SUMMARY__")
    # 写小结：补最旧的那个待补日；没有待补就写今天
    if is_summary and p["pending_summaries"]:
        log_date = p["pending_summaries"][0]
    else:
        log_date = today
    d = log_dir(pid)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{log_date}.md")
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write(f"# 学习日志 · {pid} · {log_date}\n\n")
        stamp = datetime.now().strftime("%H:%M")
        f.write(f"## [{stamp}] {args.node}\n\n{body}\n\n")
    refresh_locks(p, cur)
    if args.node in cm:
        p["current_focus"] = args.node
        s = p["nodes"][args.node]
        if s["status"] == "available":
            s["status"] = "learning"
            s["history"].append({"date": today, "event": "start", "score": None})
    elif not is_summary:
        print(f"（注意：节点 {args.node} 不在本包课程里，已作为自由笔记记录，不影响进度。"
              f"如果是手误，用 `progress` 查正确的节点 ID。）")
    if is_summary:
        if log_date in p["pending_summaries"]:
            p["pending_summaries"].remove(log_date)   # 补完出队，nag 自然消失
        p["last_active_date"] = today
    else:
        touch_active(pid, p, today)                   # 普通学习内容才触发跨天结算
    save_progress(pid, p)
    rest = f"（还剩 {len(p['pending_summaries'])} 天待补小结）" if (is_summary and p["pending_summaries"]) else ""
    print(f"已追加到 logs/{pid}/{log_date}.md（节点 {args.node}）{rest}")


def cmd_master(args):
    pid = resolve_pack(args.pack)
    try:
        score = int(args.score)
    except (ValueError, TypeError):
        die(f"score 必须是 1-5 的整数（你给的是 {args.score!r}）")
    if not 1 <= score <= 5:
        die("score 必须是 1-5")
    p, cur = load_progress(pid)
    cm = cur_map(cur)
    refresh_locks(p, cur)
    if args.node not in cm:
        die(f"未知节点：{args.node}（本包 {pid}）。用 `progress` 看有哪些节点。")
    s = p["nodes"][args.node]
    if s["status"] == "locked":
        deps = cm[args.node].get("deps", [])
        die(f"{args.node} 还锁着（前置未达标），不能直接测验/跳级。"
            f"先通过它的前置：{', '.join(deps) or '（无）'}")
    today = today_str()
    s["last_score"] = score
    notes = []
    # 置信度校准（可选）
    if args.confidence:
        s["confidence_log"].append({"date": today, "score": score, "confidence": args.confidence})

    # Bloom 门禁：节点有 required bloom 时，达标必须测到该层级，否则不计入掌握（搬进引擎，不靠自觉）
    required = cm[args.node].get("bloom")
    bloom_ok = True
    if score >= 4 and required in BLOOM_LEVELS:
        if args.bloom in BLOOM_LEVELS:
            if BLOOM_LEVELS.index(args.bloom) < BLOOM_LEVELS.index(required):
                bloom_ok = False
                notes.append(f"⚠️ 本节要求测到「{required}」层级，本次只到「{args.bloom}」→ 不计入掌握，停在 learned")
            else:
                idx = BLOOM_LEVELS.index(args.bloom)
                if idx > (BLOOM_LEVELS.index(s["bloom_reached"]) if s.get("bloom_reached") in BLOOM_LEVELS else -1):
                    s["bloom_reached"] = args.bloom
        else:
            notes.append(f"⚠️ 没用 --bloom 声明测验层级（本节要求「{required}」）→ 掌握判定存疑，请声明")

    # 掌握判定：达标 + 跨天 才升 mastered（防同一天同一题连答两次秒过）
    if score >= 4 and bloom_ok:
        prev_sd = s.get("last_streak_date")
        s["streak"] += 1
        if s["streak"] >= 2 and prev_sd is not None and prev_sd != today:
            s["status"] = "mastered"
        else:
            s["status"] = "learned"
            if s["streak"] >= 2 and prev_sd == today:
                notes.append("（连续两次达标但在同一天 → 暂停在 learned，隔天再达标一次才升『已掌握』）")
        s["last_streak_date"] = today
    elif score >= 4 and not bloom_ok:
        if s["status"] != "mastered":
            s["status"] = "learned"   # 达标但层级不够：记 learned，streak 不增、不升 mastered
    else:
        s["streak"] = 0
        s["last_streak_date"] = None
        s["status"] = "learning"
    schedule(s, score, today)
    s["history"].append({"date": today, "event": "quiz", "score": score,
                          "confidence": args.confidence, "bloom": args.bloom})
    touch_active(pid, p, today)
    refresh_locks(p, cur)
    save_progress(pid, p)
    if args.confidence == "high" and score < 4:
        notes.append("⚠️ 自信却没达标 → 记入校准危险区，下次重点复测")
    print(f"{args.node} → 评分 {score}，状态 {s['status']}，连续达标 {s['streak']}，下次复习 {s['next_review']}")
    for n in notes:
        print(f"   {n}")
    newly = [nid for nid, node in cm.items()
             if p["nodes"][nid]["status"] == "available" and args.node in node.get("deps", [])]
    if newly:
        print(f"解锁后继：{', '.join(newly)}")


def cmd_review(args):
    today = today_str()
    pids = list_installed() if args.all else [resolve_pack(args.pack)]
    any_due = False
    for pid in pids:
        p = peek_progress(pid)
        cur = peek_curriculum(pid)
        if not p or not cur:
            continue
        cm = cur_map(cur)
        due = _due_nodes(p, cur, today)
        relearn = _relearn_due(p, cur, today)
        if not due and not relearn:
            continue
        any_due = True
        if due:
            print(f"[{pid}] 到期复习 {len(due)} 个：")
            for nid in due:
                s = p["nodes"][nid]
                print(f"  · {nid} {cm[nid]['title']}  (上次 {s['last_score']} 分，应复习于 {s['next_review']})")
        if relearn:
            print(f"[{pid}] 需重学 {len(relearn)} 个（上次没达标）：")
            for nid in relearn:
                s = p["nodes"][nid]
                print(f"  · {nid} {cm[nid]['title']}  (上次 {s['last_score']} 分，应重练于 {s['next_review']})")
    if not any_due:
        print("今天没有到期复习。" + ("" if args.all else "（加 --all 看所有包）"))


def _bar(done, total, width=14):
    if total == 0:
        return "·" * width
    fill = round(width * done / total)
    return "▓" * fill + "░" * (width - fill)


def _print_progress(pid, p, cur, brief=False):
    ns = cur["nodes"]
    total = len(ns)
    cnt = {k: 0 for k in ("mastered", "learned", "learning", "available", "locked")}
    for n in ns:
        st = p["nodes"].get(n["id"], {}).get("status", "locked")
        cnt[st] = cnt.get(st, 0) + 1
    done = cnt["mastered"]
    pm = load_pack_meta(pid)
    print(f"{pm.get('title', pid)}  {_bar(done, total)}  {done}/{total} 已掌握"
          f"  (已学{cnt['learned']} 在学{cnt['learning']} 可学{cnt['available']} 锁定{cnt['locked']})")
    if not brief:
        marks = {"mastered": "★", "learned": "✓", "learning": "…", "available": "○", "locked": "·"}
        for n in ns:
            s = p["nodes"].get(n["id"], {})
            mark = marks.get(s.get("status", "locked"), "·")
            bloom = s.get("bloom_reached")
            tag = f"  〔{bloom}〕" if bloom else ""
            print(f"   {mark} {n['id']} {n['title']}{tag}")


def cmd_progress(args):
    if args.all:
        for pid in list_installed():
            p = peek_progress(pid)
            cur = peek_curriculum(pid)
            if cur is None:
                print(f"{pid}: 课程文件损坏/缺失")
                continue
            if not p:
                print(f"{pid}: 未初始化")
                continue
            _print_progress(pid, p, cur, brief=True)
        return
    pid = resolve_pack(args.pack)
    p, cur = load_progress(pid)
    refresh_locks(p, cur)
    save_progress(pid, p)
    _print_progress(pid, p, cur, brief=False)


def cmd_validate(args):
    pids = list_installed() if args.all else [resolve_pack(args.pack)]
    bad = 0
    for pid in pids:
        cur = peek_curriculum(pid)
        if cur is None:
            print(f"[{pid}] ✗ curriculum.json 缺失或损坏")
            bad += 1
            continue
        probs = validate_curriculum(cur)
        errs = [m for sev, m in probs if sev == "error"]
        warns = [m for sev, m in probs if sev == "warn"]
        if errs:
            bad += 1
        if probs:
            print(f"[{pid}] {len(errs)} 个结构性问题(error) + {len(warns)} 个质量问题(warn)：")
            for m in errs:
                print(f"   ✗ {m}")
            for m in warns:
                print(f"   · {m}")
        else:
            print(f"[{pid}] ✅ 课程健康（{len(cur['nodes'])} 节点，依赖无环/无悬空/无重复，bloom 合法，目标与种子齐全）")
    if bad:
        sys.exit(1)


def cmd_audit(args):
    """深度体检：量每个节点的厚度，揪出明显比同伴单薄的『敷衍嫌疑』节点，并看前后段深度是否塌。
    专治"越往后越敷衍"——给建包流程一个确定性的 loop 依据。"""
    pids = list_installed() if args.all else [resolve_pack(args.pack)]
    for pid in pids:
        cur = peek_curriculum(pid)
        if cur is None:
            print(f"[{pid}] 课程缺失/损坏")
            continue
        nodes = cur["nodes"]
        if not nodes:
            print(f"[{pid}] 空课程")
            continue
        rows = []
        for n in nodes:
            objl = len((n.get("objective") or "").strip())
            rows.append((n.get("id"), objl, len(n.get("socratic_seeds") or []),
                         len(n.get("grounding_anchors") or [])))
        objs = sorted(r[1] for r in rows)
        median = objs[len(objs) // 2]
        half = len(rows) // 2 or 1
        avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
        fh = avg([r[1] for r in rows[:half]])
        lh = avg([r[1] for r in rows[half:]])
        sag = (fh and lh < fh * 0.7)
        head = (f"  ⚠️ 后半段比前半段薄 {round((fh - lh) / fh * 100) if fh else 0}%（典型『越往后越敷衍』）"
                if sag else "  ✅ 前后段深度均匀")
        print(f"[{pid}] {len(rows)} 节点 | objective 字数：中位 {median}，前半均 {fh}，后半均 {lh}{head}")
        thin = [r for r in rows if r[1] < max(20, median * 0.5) or r[2] < 2 or r[3] == 0]
        if thin:
            print(f"  敷衍嫌疑 {len(thin)} 个（objective 过短 / 种子<2 / 无对标锚点）：")
            for rid, ol, ns, na in thin:
                print(f"    · {rid}  objective {ol}字  种子 {ns}  对标 {na}")
        else:
            print("  ✅ 没有明显单薄的节点")


def cmd_skip_summary(args):
    """放弃某个/全部待补的当日小结，把永久 nag 清掉（不写小结也能脱困）。"""
    pid = resolve_pack(args.pack)
    p, cur = load_progress(pid)
    p.setdefault("pending_summaries", [])
    if args.all:
        n = len(p["pending_summaries"])
        p["pending_summaries"] = []
        print(f"已放弃全部 {n} 个待补小结。")
    elif args.date:
        if args.date in p["pending_summaries"]:
            p["pending_summaries"].remove(args.date)
            print(f"已放弃 {args.date} 的小结。")
        else:
            print(f"{args.date} 不在待补列表：{p['pending_summaries'] or '（空）'}")
    elif p["pending_summaries"]:
        d = p["pending_summaries"].pop(0)
        print(f"已放弃最旧的待补小结 {d}。")
    else:
        print("没有待补小结。")
    save_progress(pid, p)


def cmd_miss(args):
    pid = resolve_pack(args.pack)
    sub = args.miss_cmd
    data = load_miscon(pid)
    if sub == "add":
        body = sys.stdin.read().strip()
        if not body:
            die("miss add 需要从 stdin 传入正文。")
        nid = args.node or "-"
        existing = [int(m["id"][1:]) for m in data["items"]
                    if isinstance(m.get("id"), str) and m["id"].startswith("M") and m["id"][1:].isdigit()]
        new_id = "M%03d" % ((max(existing) + 1) if existing else 1)
        data["items"].append({"id": new_id, "node": nid, "text": body,
                              "status": "open", "retests": 0,
                              "created": today_str(), "resolved": None})
        save_miscon(pid, data)
        print(f"已记录误概念 [{new_id}] ({nid}) → state/{pid}/misconceptions.json")
    elif sub == "list":
        items = data["items"]
        if args.open_only:
            items = [m for m in items if m["status"] == "open"]
        if not items:
            print("（无）")
            return
        for m in items:
            box = "[ ]" if m["status"] == "open" else "[x]"
            print(f"  {box} {m['id']} ({m.get('node','-')}) 复测{m.get('retests',0)}次  {m['text']}")
    elif sub == "retest":
        for m in data["items"]:
            if m["id"] == args.id:
                m["retests"] = m.get("retests", 0) + 1
                save_miscon(pid, data)
                print(f"{args.id} 复测+1（共 {m['retests']} 次），仍为 {m['status']}")
                return
        die(f"找不到 {args.id}")
    elif sub == "resolve":
        for m in data["items"]:
            if m["id"] == args.id:
                m["status"] = "retired"
                m["resolved"] = today_str()
                save_miscon(pid, data)
                print(f"{args.id} 已纠正 → retired")
                return
        die(f"找不到 {args.id}")


# ============================ 参数解析 ============================
def main():
    p = argparse.ArgumentParser(description="通用苏格拉底式学习系统状态引擎")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_pack_arg(sp):
        sp.add_argument("--pack", help="指定学习包（默认用当前 active 包）")

    s = sub.add_parser("packs"); s.set_defaults(fn=cmd_packs)
    s = sub.add_parser("new-pack"); s.add_argument("id"); s.add_argument("title", nargs="?")
    s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_new_pack)
    s = sub.add_parser("install"); s.add_argument("id"); s.set_defaults(fn=cmd_install)
    s = sub.add_parser("use"); s.add_argument("id"); s.set_defaults(fn=cmd_use)

    s = sub.add_parser("init"); add_pack_arg(s); s.add_argument("--force", action="store_true"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("boot"); add_pack_arg(s); s.set_defaults(fn=cmd_boot)
    s = sub.add_parser("log"); add_pack_arg(s); s.add_argument("node"); s.set_defaults(fn=cmd_log)
    s = sub.add_parser("master"); add_pack_arg(s); s.add_argument("node"); s.add_argument("score")
    s.add_argument("--confidence", choices=CONF_LEVELS); s.add_argument("--bloom", choices=BLOOM_LEVELS)
    s.set_defaults(fn=cmd_master)
    s = sub.add_parser("review"); add_pack_arg(s); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_review)
    s = sub.add_parser("progress"); add_pack_arg(s); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_progress)
    s = sub.add_parser("validate"); add_pack_arg(s); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_validate)
    s = sub.add_parser("audit"); add_pack_arg(s); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("skip-summary"); add_pack_arg(s)
    s.add_argument("date", nargs="?"); s.add_argument("--all", action="store_true"); s.set_defaults(fn=cmd_skip_summary)

    s = sub.add_parser("miss"); add_pack_arg(s)
    msub = s.add_subparsers(dest="miss_cmd", required=True)
    ms = msub.add_parser("add"); ms.add_argument("node", nargs="?"); ms.set_defaults(fn=cmd_miss)
    ms = msub.add_parser("list"); ms.add_argument("--open-only", action="store_true"); ms.set_defaults(fn=cmd_miss)
    ms = msub.add_parser("retest"); ms.add_argument("id"); ms.set_defaults(fn=cmd_miss)
    ms = msub.add_parser("resolve"); ms.add_argument("id"); ms.set_defaults(fn=cmd_miss)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
