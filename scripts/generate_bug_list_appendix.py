#!/usr/bin/env python
"""后处理：从 classification_data.json 生成各分类完整 Bug 清单附录

用法:
  uv run python scripts/generate_bug_list_appendix.py
  uv run python scripts/generate_bug_list_appendix.py --json outputs/classification_data.json --output outputs/report_refined_complete.md

基本原理:
  1. 读取 classification_data.json（全量结构化数据）
  2. 按 root_cause_category + fix_status 分组
  3. 生成完整的 Markdown 附录
  4. 附加到 report_refined.md 尾部，或输出独立文件
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_JSON = BASE_DIR / "outputs" / "classification_data.json"
DEFAULT_REPORT = BASE_DIR / "outputs" / "report_refined.md"
DEFAULT_OUTPUT = BASE_DIR / "outputs" / "report_refined_complete.md"


def load_data(json_path: Path) -> list[dict]:
    if not json_path.exists():
        print(f"[错误] 找不到 JSON 文件: {json_path}", file=sys.stderr)
        sys.exit(1)
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def group_bugs(bugs: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """按 根因分类 → 修复状态 分组"""
    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for bug in bugs:
        cat = bug.get("root_cause_category", "未分类") or "未分类"
        status = bug.get("fix_status", "未知") or "未知"
        grouped[cat][status].append(bug)
    return grouped


def bug_to_row(bug: dict) -> str:
    """单条 Bug → Markdown 表格行"""
    bug_id = bug.get("bug_id", "无 ID")
    title = (bug.get("title") or "无标题").strip()
    root_cause = (bug.get("parsed_root_cause") or bug.get("status") or "无").strip()[:200]
    fix_method = (bug.get("parsed_fix_method") or "无").strip()[:200]
    keywords = (bug.get("matched_keywords") or "").strip()
    return f"| {bug_id} | {title} | {root_cause} | {fix_method} | {keywords} |"


def generate_appendix(bugs: list[dict]) -> str:
    grouped = group_bugs(bugs)
    total = len(bugs)

    lines = [
        "\n---\n",
        "# 附录：各分类完整 Bug 清单",
        f"\n> 本附录由 `scripts/generate_bug_list_appendix.py` 自动生成",
        f"> 数据来源: {DEFAULT_JSON.name}",
        f"> 生成时间: 自动生成",
        f"> 总计: {total} 条 Bug\n",
    ]

    # 按分类 Bug 数降序排列
    sorted_categories = sorted(grouped.items(), key=lambda x: sum(len(v) for v in x[1].values()), reverse=True)

    for cat, status_groups in sorted_categories:
        total_in_cat = sum(len(v) for v in status_groups.values())
        lines.append(f"\n## {cat}（共 {total_in_cat} 条）\n")

        for status in ["已修复", "未修复/挂起", "无法复现", "未知"]:
            bugs_in_status = status_groups.get(status, [])
            if not bugs_in_status:
                continue
            lines.append(f"### {status}（{len(bugs_in_status)} 条）\n")
            lines.append("| Bug ID | Title | 根因 | 修复方式 | 匹配关键词 |")
            lines.append("|--------|-------|------|----------|-----------|")
            for bug in bugs_in_status:
                lines.append(bug_to_row(bug))
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="生成完整 Bug 清单附录")
    parser.add_argument("--json", default=str(DEFAULT_JSON), help="classification_data.json 路径")
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="report_refined.md 路径（可选）")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出文件路径")
    parser.add_argument("--standalone", action="store_true", help="仅输出附录文件，不拼接报告")
    args = parser.parse_args()

    json_path = Path(args.json)
    report_path = Path(args.report)
    output_path = Path(args.output)

    bugs = load_data(json_path)
    print(f"[APPENDIX] 读取 {len(bugs)} 条分类数据")

    appendix = generate_appendix(bugs)
    appendix_size = len(appendix.split("\n"))
    print(f"[APPENDIX] 附录共 {appendix_size} 行")

    if args.standalone:
        output_path.write_text(appendix, encoding="utf-8")
        print(f"[APPENDIX] 附录已写入: {output_path}")
        return

    # 拼接报告 + 附录
    if report_path.exists():
        report = report_path.read_text(encoding="utf-8")

        # 移除末尾已有的分隔线和附录
        if "# 附录" in report:
            report = report.split("# 附录")[0].rstrip()
            report = report.rstrip("---").rstrip()

        combined = report.rstrip() + "\n\n" + appendix
        output_path.write_text(combined, encoding="utf-8")
        print(f"[APPENDIX] 已拼接报告 + 附录 → {output_path}")
        print(f"         原始报告: {len(report.split(chr(10)))} 行")
        print(f"         附录: {appendix_size} 行")
        print(f"         总计: {len(combined.split(chr(10)))} 行")
    else:
        output_path.write_text(appendix, encoding="utf-8")
        print(f"[APPENDIX] 报告不存在 ({report_path})，仅输出附录 → {output_path}")


if __name__ == "__main__":
    main()
