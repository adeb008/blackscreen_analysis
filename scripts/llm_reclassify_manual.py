#!/usr/bin/env python
"""LLM 批量精校脚本：将所有"需人工判断"的 Bug 喂给 DeepSeek 重新分类

原理:
  1. 从 classification_data.json 读取全部 Bug
  2. 筛选 root_cause_category = "需人工判断"
  3. 分批（20条/批）发送给 DeepSeek
  4. LLM 返回精校后分类（从 25 类中选择）
  5. 更新 classification_data.json + analyzed_bugs.json

用法:
  uv run python scripts/llm_reclassify_manual.py
  uv run python scripts/llm_reclassify_manual.py --dry-run    # 仅预览，不写回
  uv run python scripts/llm_reclassify_manual.py --batch 10   # 每批 10 条
  uv run python scripts/llm_reclassify_manual.py --max 50     # 只精校前 50 条
  uv run python scripts/llm_reclassify_manual.py --all        # 审查全部已有分类（不只是需人工判断）
  uv run python scripts/llm_reclassify_manual.py --all --max 100    # 审查前100条
"""

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# 加载 .env
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "outputs" / "classification_data.json"
KB_PATH = BASE_DIR / "black_screen_data" / "analyzed_bugs.json"

# ── DeepSeek 配置 ──
API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_ANTHROPIC_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("DEEPSEEK_ANTHROPIC_BASE_URL", "https://api.deepseek.com/v1")
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# 25 类定义（供 LLM 参考）
CATEGORY_LIST = """
1. 应用crash-空指针/NPE — NullPointerException、空指针解引用
2. 应用crash-ANR — 应用无响应、Input dispatching timed out
3. 应用crash-Native/SIG — SIGSEGV/SIGABRT、tombstone、native crash
4. 应用crash-Observer泄漏 — ContentObserver 未反注册、重复注册
5. 应用crash-跨进程/序列化 — Binder/AIDL/IPC 异常
6. 应用crash-三方应用 — 第三方应用异常（讯飞/雄狮/高德等）
7. QNX-SAIL/safetymonitor — SAIL 75ms超时、功能安全事件、pshold 拉低
8. QNX-IDPS/Kernel — IDPS crash、kernel panic/shutdown
9. QNX-SPI/心跳/通信 — SPI 通信中断、心跳丢失、io-sock/emac 驱动挂死
10. QNX-启动/STR唤醒 — STR 休眠唤醒异常、suspend/resume 失败
11. 硬件-NOC/DDR/900E — NOC Error、DDR 错误、900E/9008 高通底层异常
12. 硬件-显示屏/解串器 — 解串器 SerDes 异常、DSI/LVDS link down
13. 硬件-电源/供电 — 电源/供电异常、电流不足、电压波动
14. 系统-升级/回滚/配置 — OTA/FOTA 升级失败、版本回滚、配置错误
15. 系统-分区/存储损坏 — userdata/metadata 分区损坏、断电导致
16. 系统-PAG/动画库 — PAG/Lottie 动画渲染异常、GPU 渲染问题
17. 系统-进程freeze/冻结 — system_server 冻结、进程 freeze、冻屏
18. 系统-内存踩踏 — 踩内存/memory corruption、use-after-free
19. 系统-surface/fd泄漏 — SurfaceFlinger FD 泄漏、too many open files
20. 环境-台架/线束/电源不稳 — 台架环境、线束接触不良、串口板
21. 环境-测试手法/工具 — dumpstate/monkey 等测试操作
22. 环境-温度/高温 — 高温测试、thermal 触发
23. 场景-CarPlay/Carlink — 手机互联、CP 连接回连
24. 场景-倒车/AVM — 倒车、全景影像、R 档切换
"""


def _load_golden_examples() -> dict:
    """加载金标准案例，供 few-shot prompting"""
    gp = Path(__file__).resolve().parent.parent / "outputs" / "golden_examples.json"
    if not gp.exists():
        return {}
    try:
        return json.loads(gp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _build_few_shot_section(golden: dict) -> str:
    """用金标准案例构建 few-shot 提示区段"""
    lines = []
    order = [
        "应用crash-空指针/NPE", "应用crash-ANR", "应用crash-Native/SIG",
        "应用crash-Observer泄漏", "应用crash-跨进程/序列化", "应用crash-三方应用",
        "QNX-SAIL/safetymonitor", "QNX-IDPS/Kernel", "QNX-SPI/心跳/通信", "QNX-启动/STR唤醒",
        "硬件-NOC/DDR/900E", "硬件-显示屏/解串器", "硬件-电源/供电",
        "系统-升级/回滚/配置", "系统-分区/存储损坏", "系统-PAG/动画库",
        "系统-进程freeze/冻结", "系统-内存踩踏", "系统-surface/fd泄漏",
        "环境-台架/线束/电源不稳", "环境-测试手法/工具", "环境-温度/高温",
        "场景-CarPlay/Carlink", "场景-倒车/AVM", "场景-USB/媒体",
    ]
    for cat in order:
        examples = golden.get(cat, [])
        if not examples:
            lines.append(f"  {order.index(cat)+1}. {cat} — （暂无金标准案例）")
            continue
        lines.append(f"  {order.index(cat)+1}. {cat}")
        for ex in examples[:3]:
            tid = ex.get("title", "")[:80]
            lines.append(f"     案例: [{ex['bug_id']}] {tid}")
            rc = ex.get("root_cause", "")[:100]
            if rc:
                lines.append(f"     根因: {rc}")
            kw = ex.get("keywords", "")
            if kw:
                lines.append(f"     命中词: {kw}")
    return "\n".join(lines)


GOLDEN = _load_golden_examples()
FEW_SHOT_SECTION = _build_few_shot_section(GOLDEN) if GOLDEN else ""


SYSTEM_PROMPT = f"""你是一位车载座舱黑屏/卡死/闪屏问题分析专家。你的任务是对每条 Bug 做根因分类精校。

当前分类体系（可动态扩展）及金标准案例：
{FEW_SHOT_SECTION}

精校原则：
- 根据 Bug 的 Title、Comments、Cause Analysis 等文本判断最合适的分类
- 如果文本包含明确的根因描述 → 归入对应分类
- 如果文本模糊但有线索 → 归入最可能的分类，置信度标"中"
- 如果完全无法判断（空文本/无意义内容）→ 保留"需人工判断"，置信度标"低"
- **注意否定语义**：如果文本明确说"不是X问题"，不要归入X类
- **新分类发现**：如果某条Bug的根因模式在当前25类中找不到匹配，且符合以下条件，可以提出新分类：
  条件：① 该Bug有明确的根因描述 ② 至少有3条以上类似Bug ③ 根因不属于现有任何分类
  提出方式：在"新分类建议"列填写建议的分类名（格式：领域-子类名，如"场景-蓝牙/电话"）

输出格式（严格 Markdown 表格，不要加额外说明）：
| Bug ID | 精校后分类 | 置信度 | 判断依据（15字内） | 新分类建议 |
|-------|-----------|-------|-----------------|----------|
（新分类建议列：如果现有25类可覆盖则留空，如果需要新分类则填建议名称）"""

REVIEW_ALL_PROMPT = f"""你是一位车载座舱黑屏/卡死/闪屏问题分析专家。你的任务是审查每条 Bug 的现有分类是否合理。

当前分类体系（可动态扩展）及金标准案例：
{FEW_SHOT_SECTION}

审查原则：
- 如果现有分类合理 → 保持不变，置信度标"高"
- 如果现有分类明显错误（如蓝牙HFP被分到硬件类）→ 纠正，置信度标"高"
- 如果现有分类不够精确（如通用类可细化）→ 纠正到更精确的分类，置信度标"中"
- 如果文本信息不足无法判断 → 保持不变，置信度标"中"
- **新分类发现**：如果该Bug的根因模式在当前分类体系中找不到匹配，在"新分类建议"列提出

输出格式（严格 Markdown 表格，不要加额外说明）：
| Bug ID | 现有分类 | 审查后分类 | 置信度 | 变更原因（15字内）| 新分类建议 |
|-------|---------|-----------|-------|-----------------|----------|
（新分类建议列：现有分类可覆盖则留空，否则填建议名称，格式：领域-子类名）"""


def load_data(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[错误] 找不到 {path}")
        sys.exit(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: list[dict]):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def call_deepseek(batch: list[dict], batch_num: int, total_batches: int) -> str:
    """调用 DeepSeek API 精校一批 Bug"""
    from openai import OpenAI

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # 构建这批 Bug 的数据
    lines = []
    for bug in batch:
        bid = bug.get("bug_id", "无 ID")
        title = (bug.get("title") or "-")[:200]
        comments = (bug.get("comments") or "-")[:300]
        rc = (bug.get("parsed_root_cause") or "-")[:200]
        keywords = (bug.get("matched_keywords") or "-")
        lines.append(
            f"- Bug ID: {bid}\n  Title: {title}\n  Comments: {comments}\n  RootCause: {rc}\n  Keywords: {keywords}"
        )

    user_msg = f"""以下是第 {batch_num}/{total_batches} 批待精校的 Bug（共 {len(batch)} 条）：

{"".join(lines)}

请对每条 Bug 给出精校后的分类，输出 Markdown 表格。不要加任何额外的说明文字。"""

    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=2000,
                timeout=300,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt < 2:
                wait = 20 * (attempt + 1)
                print(f"  ⚠️ 第{attempt+1}次重试 ({wait}s后)...")
                time.sleep(wait)
            else:
                print(f"  ❌ 第{attempt+1}次重试失败: {e}")
    return ""


def call_deepseek_review(batch: list[dict], batch_num: int, total_batches: int) -> str:
    """调用 DeepSeek 审查已有分类"""
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    lines = []
    for bug in batch:
        bid = bug.get("bug_id", "")
        current_cat = bug.get("root_cause_category", "未知")
        title = (bug.get("title") or "-")[:200]
        comments = (bug.get("comments") or "-")[:300]
        rc = (bug.get("parsed_root_cause") or "-")[:200]
        lines.append(
            f"- Bug ID: {bid}\n  现有分类: {current_cat}\n  Title: {title}\n  Comments: {comments}\n  RootCause: {rc}"
        )
    
    user_msg = f"第 {batch_num}/{total_batches} 批（共 {len(batch)} 条）：\n\n{''.join(lines)}"
    
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=MODEL, messages=[{"role": "system", "content": REVIEW_ALL_PROMPT}, {"role": "user", "content": user_msg}],
                temperature=0.1, max_tokens=2000, timeout=300,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            if attempt < 2:
                time.sleep(20 * (attempt + 1))
            else:
                print(f"  ❌ 第{attempt+1}次重试失败: {e}")
    return ""


def parse_response(text: str, is_review: bool = False) -> dict[str, dict]:
    """从 LLM 返回的 Markdown 表格中解析精校结果

    支持格式（最后一列为可选的新分类建议）:
      - review=False: | Bug ID | 分类 | 置信度 | 判断依据 | [新分类建议] |   (5列)
      - review=True:  | Bug ID | 现有分类 | 审查后分类 | 置信度 | 变更原因 | [新分类建议] |  (6列)

    返回: {bug_id: {"category": str, "confidence": str, "reason": str, "new_category": str}}
    """
    results = {}

    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        
        parts = [p.strip() for p in line.split("|")[1:-1]]
        n = len(parts)
        
        # 跳过表头和分隔行
        if not parts or parts[0].lower() in ("bug id", "bug_id", "---", ":---", "-"):
            continue
        if n < 3:
            continue
        
        bug_id = parts[0]
        new_category = ""
        
        if is_review:
            # 审查模式: BugID | 现有分类 | 审查后分类 | 置信度 | 变更原因 | [新分类建议]
            if n >= 4:
                category = parts[2]
                confidence = parts[3]
                reason = parts[4] if n >= 5 else ""
                new_category = parts[5] if n >= 6 else ""
            else:
                continue
        else:
            # 精校模式: BugID | 分类 | 置信度 | 判断依据 | [新分类建议]
            if n >= 3:
                category = parts[1]
                confidence = parts[2]
                reason = parts[3] if n >= 4 else ""
                new_category = parts[4] if n >= 5 else ""
            else:
                continue
        
        # 清理分类名（去掉序号前缀）
        category = re.sub(r"^\d+[.\s]+", "", category).strip()
        if "---" in category:
            continue
        
        results[bug_id] = {
            "category": category,
            "confidence": confidence,
            "reason": reason[:100] if reason else "",
            "new_category": new_category,
        }
    
    return results


def update_classification_json(
    all_bugs: list[dict], results: dict[str, dict]
) -> tuple[int, int]:
    """更新 classification_data.json 中的 classification 结果

    返回: (已更新数, 变更数)
    """
    updated = 0
    changed = 0
    for bug in all_bugs:
        bid = bug.get("bug_id", "")
        if bid in results:
            old_cat = bug.get("root_cause_category", "")
            new_cat = results[bid]["category"]
            bug["root_cause_category"] = new_cat
            updated += 1
            if old_cat != new_cat and old_cat != new_cat:
                changed += 1

    save_json(JSON_PATH, all_bugs)
    return updated, changed


def update_kb(results: dict[str, dict]):
    """更新 analyzed_bugs.json 中的 category 字段"""
    if not KB_PATH.exists():
        print(f"  ⚠️ KB 文件不存在，跳过 KB 更新")
        return

    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)

    bugs = kb.get("bugs", {})
    updated = 0
    for bid, info in results.items():
        if bid in bugs:
            old_cat = bugs[bid].get("category", "")
            new_cat = info["category"]
            if new_cat and new_cat != old_cat:
                bugs[bid]["category"] = new_cat
                bugs[bid]["refined_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                updated += 1

    # 重新计算趋势
    from collections import Counter

    cat_fixed, cat_total, mod_ct = {}, {}, {}
    for b in bugs.values():
        cat = b.get("category", "未分类")
        mod = b.get("module", "未知")
        cat_total[cat] = cat_total.get(cat, 0) + 1
        mod_ct[mod] = mod_ct.get(mod, 0) + 1
        if b.get("fix_status") == "已修复" or str(b.get("status", "")).lower() in ("closed", "confirm"):
            cat_fixed[cat] = cat_fixed.get(cat, 0) + 1

    category_trend = {}
    for cat, total in sorted(cat_total.items(), key=lambda x: -x[1]):
        fixed = cat_fixed.get(cat, 0)
        rate = fixed / total * 100 if total > 0 else 0
        trend = "✅ 收敛" if rate >= 80 else ("🔶 收敛中" if rate >= 50 else "🔴 需关注")
        category_trend[cat] = {"total": total, "fixed": fixed, "fix_rate": round(rate, 1), "trend": trend}

    kb["_meta"]["category_trend"] = category_trend
    kb["_meta"]["module_heatmap"] = dict(sorted(mod_ct.items(), key=lambda x: -x[1])[:15])
    kb["_meta"]["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 追加历史快照
    snapshot = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(bugs),
        "categories": dict(sorted(cat_total.items(), key=lambda x: -x[1])),
        "modules": dict(sorted(mod_ct.items(), key=lambda x: -x[1])[:20]),
        "fix_status": dict(Counter(b.get("fix_status", "未知") for b in bugs.values()).most_common()),
        "severity": dict(Counter(b.get("severity", "未知") for b in bugs.values()).most_common()),
    }
    history = kb["_meta"].setdefault("run_history", [])
    if not history or history[-1].get("timestamp", "")[:10] != snapshot["timestamp"][:10]:
        history.append(snapshot)
        if len(history) > 50:
            kb["_meta"]["run_history"] = history[-50:]

    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)

    print(f"  ✅ KB 已更新: {updated} 条分类变更")


def main():
    parser = argparse.ArgumentParser(description="LLM 批量精校：需人工判断 Bug")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写回")
    parser.add_argument("--batch", type=int, default=20, help="每批条数（默认 20）")
    parser.add_argument("--max", type=int, default=0, help="最大精校条数（默认全部）")
    parser.add_argument("--all", dest="review_all", action="store_true", help="审查全部已有分类（不只是需人工判断）")
    args = parser.parse_args()

    if not API_KEY:
        print("[错误] 请设置 DEEPSEEK_API_KEY 环境变量")
        sys.exit(1)

    print(f"🔍 读取 {JSON_PATH}...")
    all_bugs = load_data(JSON_PATH)

    # 筛选 Bug
    if args.review_all:
        print("\n[1/4] 审查全部已有分类（所有 {} 条 Bug）...".format(len(all_bugs)))
        target_bugs = all_bugs
        use_review_mode = True
    else:
        print("\n[1/4] 筛选需人工判断的 Bug...")
        target_bugs = [b for b in all_bugs if b.get("root_cause_category") == "需人工判断"]
        use_review_mode = False
    if args.max > 0:
        target_bugs = target_bugs[:args.max]

    total = len(target_bugs)
    print(f"\n📊 统计:")
    print(f"   Bug 总数: {len(all_bugs)}")
    mode_label = "审查" if use_review_mode else "需人工判断"
    print(f"   {mode_label}: {total}")
    if args.max > 0:
        print(f"   本次精校: 前 {args.max} 条")

    if args.dry_run:
        print(f"\n🔍 DRY RUN — 仅展示，不调用 API")
        for bug in target_bugs[:5]:
            print(f"   - {bug.get('bug_id')}: {bug.get('title', '')[:60]}")
        if len(target_bugs) > 5:
            print(f"   ... 还有 {len(target_bugs) - 5} 条未展示")
        return

    if total == 0:
        print("✅ 没有符合条件的 Bug")
        return

    # 全量审查安全限制
    if use_review_mode and not args.max and total > 100:
        print(f"⚠️ 审查全部 {total} 条 Bug 费用较高")
        print(f"   建议使用: --all --max 50  或  --all --max 100")
        response = input("   是否继续全部审查? (y/N): ").strip().lower()
        if response != 'y':
            print("已取消")
            return

    # 分批
    batch_size = args.batch
    batches = [target_bugs[i:i+batch_size] for i in range(0, total, batch_size)]
    total_batches = len(batches)

    all_results: dict[str, dict] = {}

    mode_str = "审查" if args.review_all else "精校"
    print(f"\n🚀 开始分批{total_batches}批 {batch_size}条/批)...")

    for i, batch in enumerate(batches, 1):
        print(f"\n--- 第 {i}/{total_batches} 批 ({len(batch)} 条) ---")
        response = call_deepseek_review(batch, i, total_batches) if use_review_mode else call_deepseek(batch, i, total_batches)

        if not response:
            print(f"  ❌ 本批调用失败，跳过")
            continue

        results = parse_response(response, is_review=use_review_mode)
        print(f"  📝 LLM 返回 {len(results)} 条结果")

        if results:
            for bid, info in list(results.items())[:3]:
                print(f"     {bid}: {info['category']} ({info['confidence']})")
            if len(results) > 3:
                print(f"     ... 还有 {len(results)-3} 条")

        all_results.update(results)

        # 批次间加间隔，避免速率限制
        if i < total_batches:
            time.sleep(1)

    # 汇总
    total_results = len(all_results)
    print(f"\n{'='*50}")
    print(f"📊 {mode_str}汇总")
    print(f"{'='*50}")
    print(f"   总提交{mode_str}: {total} 条")
    print(f"   成功{mode_str}: {total_results} 条")

    if total_results > 0:
        # 分类统计
        cat_counter = Counter(r["category"] for r in all_results.values())
        low_conf = sum(1 for r in all_results.values() if r["confidence"] in ("低", "低置信度"))
        med_conf = sum(1 for r in all_results.values() if r["confidence"] in ("中", "中等"))
        high_conf = sum(1 for r in all_results.values() if r["confidence"] in ("高", "高置信度"))

        print(f"   Top 5 分类:")
        for cat, cnt in cat_counter.most_common(5):
            print(f"      {cat}: {cnt}")
        print(f"   置信度分布: 高={high_conf} 中={med_conf} 低={low_conf}")

    # 收集新分类建议
    new_cats: dict[str, list[str]] = {}
    for bid, info in all_results.items():
        nc = info.get("new_category", "").strip()
        if nc and nc != "需人工判断":
            new_cats.setdefault(nc, []).append(bid)
    
    if new_cats:
        print(f"\n🆕 发现 {len(new_cats)} 个新分类建议:")
        pending_path = BASE_DIR / "outputs" / "pending_categories.json"
        existing_pending = {}
        if pending_path.exists():
            try:
                existing_pending = json.loads(pending_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        for cat, bids in new_cats.items():
            # 断链2修复: pending 中附带 bug_texts，供 generate_keywords 调 LLM 使用
            bug_texts = []
            for bid in bids:
                info = all_results.get(bid, {})
                text = info.get("title") or info.get("description") or info.get("summary") or ""
                bug_texts.append(str(text).strip())

            if cat in existing_pending:
                old_entry = existing_pending[cat]
                # 兼容旧格式（list）
                if isinstance(old_entry, list):
                    old_entry = {"bug_ids": old_entry, "bug_texts": []}
                old_bids = set(old_entry.get("bug_ids", []))
                old_texts = old_entry.get("bug_texts", [])
                for bid, txt in zip(bids, bug_texts):
                    if bid not in old_bids:
                        old_entry["bug_ids"].append(bid)
                        old_texts.append(txt)
                old_entry["bug_texts"] = old_texts
                existing_pending[cat] = old_entry
            else:
                existing_pending[cat] = {"bug_ids": bids, "bug_texts": bug_texts}
            print(f"   {cat}: {len(bids)} 条 Bug [{', '.join(bids[:3])}{'...' if len(bids)>3 else ''}]")
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        pending_path.write_text(json.dumps(existing_pending, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n   已写入 {pending_path}")
        print(f"   确认后运行: uv run python scripts/merge_new_categories.py")
    else:
        print(f"\n   (未发现新分类建议)")

    if args.dry_run:
        print("\n🔍 DRY RUN — 未写入任何文件")
        return

    # 写回 classification_data.json
    print(f"\n💾 更新 {JSON_PATH}...")
    updated, changed = update_classification_json(all_bugs, all_results)
    print(f"   ✅ 已更新 {updated} 条，其中分类变更 {changed} 条")

    # 写回 KB
    print(f"💾 更新 {KB_PATH}...")
    update_kb(all_results)

    # 打印最终分布
    full_after = load_data(JSON_PATH)
    initial_manual = sum(1 for b in all_bugs if b.get("root_cause_category") == "需人工判断")
    final_manual = sum(1 for b in full_after if b.get("root_cause_category") == "需人工判断")
    print(f"\n{'='*50}")
    print(f"📈 精校前后对比 (全量)")
    print(f"{'='*50}")
    print(f"   需人工判断: {initial_manual} → {final_manual}")
    print(f"   成功精校: {changed} 条")
    print(f"\n✅ 精校完成")


if __name__ == "__main__":
    main()
