#!/usr/bin/env python
"""黑卡闪问题分析 — 双工作流入口

用法:
  crewai run                        # 默认工作流一: 问题分析提炼
  python main.py refine             # 工作流一: 问题分析提炼
  python main.py download           # 工作流二: Analysis 问题下载分析
  python main.py full               # 完整双工作流串联

增量跟踪:
  通过 analyzed_bugs.json 记录已分析的 Bug ID + 状态，
  后续导出只分析新增和状态变更的问题，避免重复。
"""

import json
import sys
import warnings
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from my_crew.crew import MyCrew
from my_crew.tools.bug_knowledge_tool import BugKnowledgeTool, compute_trends

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

DEFAULT_EXCEL = r"D:\my_crew\black_screen_data\Bug_20260509113654.xlsx"


def _find_latest_excel() -> str:
    """找到 black_screen_data 下最新的 Bug_*.xlsx"""
    data_dir = Path(r"D:\my_crew\black_screen_data")
    if not data_dir.exists():
        return DEFAULT_EXCEL
    xlsx_files = sorted(
        [f for f in data_dir.glob("Bug_*.xlsx") if not f.name.startswith("~$")],
        key=lambda f: f.stat().st_mtime, reverse=True
    )
    return str(xlsx_files[0]) if xlsx_files else DEFAULT_EXCEL


def _incremental_filter(excel_path: str) -> dict:
    """增量过滤: 读取 Excel，过滤掉已分析且状态未变的 Bug"""
    wb = load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    headers = [str(h) for h in rows[0]] if rows else []

    # 找 Bug ID 和 Status 列
    bug_id_col = None
    status_col = None
    for i, h in enumerate(headers):
        hl = h.lower().replace(" ", "")
        if "bugid" in hl or "bug id" in hl:
            bug_id_col = i
        if "status" in hl:
            status_col = i

    if bug_id_col is None:
        return {"new": [], "changed": [], "skipped": [], "total": 0,
                "error": "找不到 Bug ID 列"}

    # 构建 issue 列表
    issues = []
    for row in rows[1:]:
        if not row or bug_id_col >= len(row):
            continue
        bid = str(row[bug_id_col]).strip() if row[bug_id_col] else ""
        st = str(row[status_col]).strip() if status_col and status_col < len(row) else ""
        if bid:
            issues.append({"bug_id": bid, "status": st})

    result = BugKnowledgeTool.filter_new_and_changed(issues)

    # 保存本次源文件信息
    kb = BugKnowledgeTool._load_static()
    kb["_meta"]["source_file"] = Path(excel_path).name
    BugKnowledgeTool._save_static(kb)

    result["total"] = len(issues)
    return result


def _inputs(excel_path: str | None = None) -> dict:
    path = excel_path or _find_latest_excel()
    filt = _incremental_filter(path)

    new_count = len(filt.get("new", []))
    changed_count = len(filt.get("changed", []))
    skipped_count = len(filt.get("skipped", []))
    total = filt.get("total", 0)

    print(f"\n{'='*50}")
    print(f"增量过滤: {Path(path).name}")
    print(f"  总计: {total} | 新增: {new_count} | 状态变更: {changed_count} | 跳过: {skipped_count}")
    if filt.get("error"):
        print(f"  ⚠️ {filt['error']}")
    print(f"{'='*50}\n")

    return {
        "topic": "黑卡闪问题提炼分析",
        "current_year": str(datetime.now().year),
        "excel_path": str(Path(path).as_posix()),
        "new_count": str(new_count),
        "changed_count": str(changed_count),
        "skipped_count": str(skipped_count),
        "total_count": str(total),
    }


def run():
    """默认: 工作流一"""
    excel_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        MyCrew().refinement_crew().kickoff(inputs=_inputs(excel_path))
    except Exception as e:
        raise Exception(f"工作流一执行失败: {e}")


def refine():
    """工作流一: 问题分析提炼"""
    excel_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        MyCrew().refinement_crew().kickoff(inputs=_inputs(excel_path))
    except Exception as e:
        raise Exception(f"工作流一执行失败: {e}")


def download():
    """工作流二: Analysis 问题下载分析"""
    excel_path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        MyCrew().download_analysis_crew().kickoff(inputs=_inputs(excel_path))
    except Exception as e:
        raise Exception(f"工作流二执行失败: {e}")


def full():
    """完整双工作流串联"""
    excel_path = sys.argv[1] if len(sys.argv) > 1 else None
    inputs = _inputs(excel_path)
    try:
        print(">>> 工作流一: 问题分析提炼")
        MyCrew().refinement_crew().kickoff(inputs=inputs)
        print("\n>>> 工作流二: Analysis 问题下载分析")
        MyCrew().download_analysis_crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"完整工作流执行失败: {e}")


def train():
    try:
        MyCrew().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=_inputs()
        )
    except Exception as e:
        raise Exception(f"训练失败: {e}")


def replay():
    try:
        MyCrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"回放失败: {e}")


def test():
    try:
        MyCrew().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=_inputs()
        )
    except Exception as e:
        raise Exception(f"测试失败: {e}")


def run_with_trigger():
    import json
    if len(sys.argv) < 2:
        raise Exception("需要 JSON payload")
    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("无效的 JSON payload")
    inputs = _inputs()
    inputs["crewai_trigger_payload"] = trigger_payload
    try:
        return MyCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"触发执行失败: {e}")
