#!/usr/bin/env python
"""同步 analyzed_bugs.json → Obsidian 保险库

全量同步方案 D:
  A. 概览笔记 — 更新/创建黑卡闪问题提炼分析.md
  B. 分类目录 — 按 25 类分别生成笔记
  C. 趋势看板 — 分类趋势、修复状态笔记

用法:
  uv run python scripts/sync_to_obsidian.py
  uv run python scripts/sync_to_obsidian.py --dry-run    # 仅预览，不写文件
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

# ── 路径配置 ──
BASE_DIR = Path(__file__).resolve().parent.parent
OBSIDIAN_VAULT = Path(os.getenv("OBSIDIAN_VAULT_PATH",
                                r"D:\uidq1474\My Documents\Obsidian Vault"))
KB_PATH = BASE_DIR / "black_screen_data" / "analyzed_bugs.json"
JSON_PATH = BASE_DIR / "outputs" / "classification_data.json"
REPORT_PATH = BASE_DIR / "outputs" / "report_refined_complete.md"

# Obsidian 子目录
CATEGORY_DIR = "黑卡闪专项课题/分类分析"
TREND_DIR = "黑卡闪专项课题/趋势"
OVERVIEW_NOTE = "黑卡闪专项课题/黑卡闪问题提炼分析.md"


def vault_path(*parts) -> Path:
    return OBSIDIAN_VAULT.joinpath(*parts)


def sanitize_wikilink(name: str) -> str:
    """分类名 → 安全的 Obsidian 文件名和 wikilink"""
    name = name.replace("/", "_").replace("\\", "_").replace(" ", "_")
    name = re.sub(r"[<>:\"|?*]", "", name)
    return name


def load_data():
    """加载所有数据源"""
    data = {}
    if KB_PATH.exists():
        with open(KB_PATH, encoding="utf-8") as f:
            data["kb"] = json.load(f)
    if JSON_PATH.exists():
        with open(JSON_PATH, encoding="utf-8") as f:
            data["json"] = json.load(f)
    return data


def build_overview(data: dict) -> str:
    """A. 生成概览笔记"""
    kb = data.get("kb", {})
    meta = kb.get("_meta", {})
    bugs = kb.get("bugs", {})

    total = len(bugs)
    cat_trend = meta.get("category_trend", {})
    mod_heat = meta.get("module_heatmap", {})

    # 修复状态
    fix_ct = Counter(b.get("fix_status", "未知") for b in bugs.values())

    # 严重度
    sev_ct = Counter(b.get("severity", "未知") for b in bugs.values())

    # 收敛统计
    converging = sum(1 for c in cat_trend.values() if c["trend"] == "✅ 收敛")
    total_cats = len(cat_trend)
    not_converging = [c for c, v in cat_trend.items() if "🔴" in v["trend"]]

    now_str = datetime.now().strftime("%Y-%m-%d")

    lines = [
        "---",
        "title: 黑卡闪问题提炼分析",
        f'tags: ["问题分析", "自动同步"]',
        f'updated: {now_str}',
        "---",
        "",
        "# 黑卡闪问题提炼分析",
        "",
        f"> 自动同步于 {now_str} | 数据来源: analyzed_bugs.json",
        f"> 总计 **{total}** 条 Bug | **{total_cats}** 个分类",
        "",
        "---",
        "",
        "## 📊 汇总",
        "",
        f"| 指标 | 数值 |",
        f"|------|------|",
        f"| Bug 总数 | {total} |",
        f"| 分类数 | {total_cats} |",
        f"| 已修复 | {fix_ct.get('已修复', 0)} ({round(fix_ct.get('已修复',0)/total*100,1)}%) |",
        f"| 未修复/挂起 | {fix_ct.get('未修复/挂起', 0)} |",
        f"| 无法复现 | {fix_ct.get('无法复现', 0)} |",
        f"| 需人工判断 (待精校) | {cat_trend.get('需人工判断', {}).get('total', 0)} |",
        f"| 已收敛分类 | {converging}/{total_cats} |",
        "",
        "## 🔗 分类导航",
        "",
    ]

    # 按数量排序列出所有分类链接
    sorted_cats = sorted(cat_trend.items(), key=lambda x: -x[1]["total"])
    for cat, info in sorted_cats:
        wl = sanitize_wikilink(cat)
        icon = "✅" if "收敛" in info["trend"] else ("🔶" if "收敛中" in info["trend"] else "🔴")
        lines.append(
            f"- [[{wl}|{cat}]] — {info['total']}条 · 修复率 {info['fix_rate']}% {icon}"
        )

    lines += [
        "",
        "---",
        "",
        "## 📈 分布统计",
        "",
        "### 根因分类 Top 10",
        "",
        "| 分类 | 数量 | 占比 | 修复率 | 趋势 |",
        "|------|:--:|:---:|:-----:|:----:|",
    ]
    for cat, info in sorted_cats[:10]:
        pct = round(info["total"] / total * 100, 1) if total else 0
        lines.append(
            f"| [[{sanitize_wikilink(cat)}|{cat}]] | {info['total']} | {pct}% | {info['fix_rate']}% | {info['trend']} |"
        )

    lines += [
        "",
        "### 模块 Top 10",
        "",
        "| 模块 | Bug 数 |",
        "|------|:-----:|",
    ]
    for mod, cnt in sorted(mod_heat.items(), key=lambda x: -x[1])[:10]:
        lines.append(f"| {mod} | {cnt} |")

    lines += [
        "",
        "### 修复状态",
        "",
        "| 状态 | 数量 | 占比 |",
        "|------|:----:|:----:|",
    ]
    for st, cnt in fix_ct.most_common():
        lines.append(f"| {st} | {cnt} | {round(cnt/total*100,1)}% |")

    lines += [
        "",
        "### Severity 分布",
        "",
        "| 等级 | 数量 |",
        "|------|:----:|",
    ]
    for sev, cnt in sev_ct.most_common():
        lines.append(f"| {sev} | {cnt} |")

    lines += [
        "",
        "---",
        "",
        "## ⚠️ 需关注",
        "",
    ]
    if not_converging:
        lines.append("### 未收敛分类")
        for cat in not_converging:
            info = cat_trend[cat]
            wl = sanitize_wikilink(cat)
            lines.append(f"- [[{wl}|{cat}]] — {info['total']}条, 修复率 {info['fix_rate']}%")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*由 `scripts/sync_to_obsidian.py` 自动同步*")

    return "\n".join(lines)


def build_category_notes(data: dict) -> dict[str, str]:
    """B. 生成每分类笔记 → {filename: content}"""
    bugs = data.get("kb", {}).get("bugs", {})
    meta = data.get("kb", {}).get("_meta", {})
    cat_trend = meta.get("category_trend", {})

    # 按分类分组
    by_cat = defaultdict(list)
    for bid, b in bugs.items():
        cat = b.get("category", "未分类")
        by_cat[cat].append((bid, b))

    notes = {}
    for cat, bug_list in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        filename = sanitize_wikilink(cat) + ".md"
        total = len(bug_list)
        info = cat_trend.get(cat, {})
        fix_rate = info.get("fix_rate", 0)
        trend = info.get("trend", "")

        # 修复状态分组
        fixed = [(bid, b) for bid, b in bug_list if b.get("fix_status") == "已修复"]
        pending = [(bid, b) for bid, b in bug_list if b.get("fix_status") == "未修复/挂起"]
        unrepro = [(bid, b) for bid, b in bug_list if b.get("fix_status") == "无法复现"]

        lines = [
            "---",
            f'title: {cat}',
            f'tags: ["分类分析", "自动同步"]',
            "---",
            "",
            f"# {cat}",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| Bug 总数 | {total} |",
            f"| 已修复 | {len(fixed)} |",
            f"| 未修复/挂起 | {len(pending)} |",
            f"| 无法复现 | {len(unrepro)} |",
            f"| 修复率 | {fix_rate}% |",
            f"| 趋势 | {trend} |",
            "",
        ]

        if pending:
            lines += [
                "## 🚨 未修复/挂起",
                "",
                "| Bug ID | Title | Status | 根因 |",
                "|--------|-------|--------|------|",
            ]
            for bid, b in sorted(pending, key=lambda x: x[0]):
                t = (b.get("title") or "")[:60]
                s = b.get("status", "")
                rc = (b.get("root_cause") or "")[:80]
                lines.append(f"| [[{bid}]] | {t} | {s} | {rc} |")
            lines.append("")

        lines += [
            "## 📋 Bug 清单",
            "",
            "| Bug ID | Title | 状态 | 严重度 | 根因 |",
            "|--------|-------|:----:|:------:|------|",
        ]
        for bid, b in sorted(bug_list, key=lambda x: x[0]):
            t = (b.get("title") or "")[:80]
            s = b.get("status", "")
            sev = b.get("severity", "")
            rc = (b.get("root_cause") or "")[:100]
            lines.append(f"| {bid} | {t} | {s} | {sev} | {rc} |")

        lines += [
            "",
            "---",
            "",
            "[[黑卡闪问题提炼分析|← 返回总览]]",
            "",
            "*由 `scripts/sync_to_obsidian.py` 自动同步*",
        ]

        notes[filename] = "\n".join(lines)

    return notes


def build_trend_notes(data: dict) -> dict[str, str]:
    """C. 生成趋势笔记"""
    kb = data.get("kb", {})
    meta = kb.get("_meta", {})
    cat_trend = meta.get("category_trend", {})
    history = meta.get("run_history", [])

    notes = {}

    # 分类趋势
    lines = [
        "---",
        'title: 分类趋势',
        'tags: ["趋势", "自动同步"]',
        "---",
        "",
        "# 📈 分类趋势",
        "",
        f"> 基于 {len(history)} 轮历史快照",
        "",
        "## 修复率排名",
        "",
        "| 分类 | 总数 | 已修复 | 修复率 | 趋势 |",
        "|------|:---:|:-----:|:-----:|:----:|",
    ]
    for cat, info in sorted(cat_trend.items(), key=lambda x: -x[1]["total"]):
        wl = sanitize_wikilink(cat)
        lines.append(
            f"| [[{wl}|{cat}]] | {info['total']} | {info['fixed']} | {info['fix_rate']}% | {info['trend']} |"
        )

    lines += [
        "",
        "## 修复率最低的 5 个分类",
        "",
    ]
    worst = sorted(cat_trend.items(), key=lambda x: x[1]["fix_rate"])[:5]
    for cat, info in worst:
        wl = sanitize_wikilink(cat)
        lines.append(f"- 🔴 [[{wl}|{cat}]] — 修复率 {info['fix_rate']}%（{info['fixed']}/{info['total']}）")

    lines += [
        "",
        "---",
        "",
        "## 历史轮次",
        "",
        "| 轮次 | 时间 | Bug 总数 |",
        "|------|------|:-------:|",
    ]
    for i, snap in enumerate(history, 1):
        ts = snap.get("timestamp", "")[:16]
        ttl = snap.get("total", "?")
        lines.append(f"| {i} | {ts} | {ttl} |")

    lines += [
        "",
        "---",
        "",
        "[[黑卡闪问题提炼分析|← 返回总览]]",
        "",
        "*由 `scripts/sync_to_obsidian.py` 自动同步*",
    ]
    notes["分类趋势.md"] = "\n".join(lines)

    # 修复状态趋势
    lines2 = [
        "---",
        'title: 修复状态',
        'tags: ["趋势", "自动同步"]',
        "---",
        "",
        "# ✅ 修复状态",
        "",
        f"> 当前总 Bug 数: {sum(info['total'] for info in cat_trend.values())}",
        "",
        "## 各分类修复状态",
        "",
        "| 分类 | 已修复 | 未修复/挂起 | 无法复现 |",
        "|------|:-----:|:----------:|:--------:|",
    ]
    bugs_by_cat = defaultdict(list)
    for bid, b in kb.get("bugs", {}).items():
        bugs_by_cat[b.get("category", "未分类")].append(b)
    for cat in sorted(cat_trend.keys(), key=lambda c: -len(bugs_by_cat.get(c, []))):
        bl = bugs_by_cat.get(cat, [])
        f = sum(1 for b in bl if b.get("fix_status") == "已修复")
        p = sum(1 for b in bl if b.get("fix_status") == "未修复/挂起")
        u = sum(1 for b in bl if b.get("fix_status") == "无法复现")
        wl = sanitize_wikilink(cat)
        lines2.append(f"| [[{wl}|{cat}]] | {f} | {p} | {u} |")

    lines2 += [
        "",
        "---",
        "",
        "[[黑卡闪问题提炼分析|← 返回总览]]",
        "",
        "*由 `scripts/sync_to_obsidian.py` 自动同步*",
    ]
    notes["修复状态.md"] = "\n".join(lines2)

    return notes


def write_notes(notes: dict[str, str], subdir: str, dry_run: bool):
    """写入笔记到 Obsidian 子目录"""
    target_dir = vault_path(subdir)
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for filename, content in sorted(notes.items()):
        filepath = target_dir / filename
        if dry_run:
            print(f"  [DRY] {filepath.relative_to(OBSIDIAN_VAULT)} ({len(content)} bytes)")
        else:
            filepath.write_text(content, encoding="utf-8")
            print(f"  ✅ {filepath.relative_to(OBSIDIAN_VAULT)} ({len(content)} bytes)")
        written += 1
    return written


def main():
    parser = argparse.ArgumentParser(description="同步 KB → Obsidian")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    args = parser.parse_args()

    print(f"🔍 读取知识库...")
    data = load_data()
    if not data:
        print("[错误] 无法加载知识库数据")
        sys.exit(1)

    kb = data.get("kb", {})
    bugs = kb.get("bugs", {})
    meta = kb.get("_meta", {})
    cat_trend = meta.get("category_trend", {})
    mod_heat = meta.get("module_heatmap", {})

    print(f"   知识库: {len(bugs)} bugs")
    print(f"   分类: {len(cat_trend)} 类")
    print(f"   模块: {len(mod_heat)} 个")
    print(f"   历史快照: {len(meta.get('run_history', []))} 轮")

    if args.dry_run:
        print(f"\n🔍 DRY RUN — 不写文件")

    # A. 概览笔记
    print(f"\n📝 A. 概览笔记")
    overview = build_overview(data)
    overview_path = vault_path(OVERVIEW_NOTE)
    if args.dry_run:
        print(f"  [DRY] {OVERVIEW_NOTE} ({len(overview)} bytes)")
    else:
        overview_path.parent.mkdir(parents=True, exist_ok=True)
        overview_path.write_text(overview, encoding="utf-8")
        print(f"  ✅ {OVERVIEW_NOTE} ({len(overview)} bytes)")

    # B. 分类笔记
    print(f"\n📂 B. 分类笔记 ({len(cat_trend)} 个分类)")
    cat_notes = build_category_notes(data)
    n = write_notes(cat_notes, CATEGORY_DIR, args.dry_run)

    # C. 趋势笔记
    print(f"\n📈 C. 趋势笔记")
    trend_notes = build_trend_notes(data)
    n += write_notes(trend_notes, TREND_DIR, args.dry_run)

    print(f"\n{'='*50}")
    print(f"📊 同步完成")
    print(f"{'='*50}")
    print(f"   概览笔记: 1 篇")
    print(f"   分类笔记: {len(cat_notes)} 篇")
    print(f"   趋势笔记: {len(trend_notes)} 篇")
    print(f"   总计: {n + 1} 篇" if not args.dry_run else f"   总计: {n + 1} 篇（未写入）")
    print(f"   保险库: {OBSIDIAN_VAULT}")


if __name__ == "__main__":
    main()
