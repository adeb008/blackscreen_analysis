"""Bug ID 跟踪工具 — 增量分析，避免重复分析已处理的问题"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from my_crew.config import get_kb_path

TRACKING_FILE = get_kb_path()


class BugTrackerInput(BaseModel):
    """输入"""
    action: str = Field(
        default="filter",
        description="filter: 过滤未分析的问题 | mark: 标记已完成 | status: 查看统计"
    )
    bug_id: str = Field(default="", description="mark 操作时需要")
    status: str = Field(default="", description="mark 操作时的问题状态")
    report_path: str = Field(default="", description="mark 操作时的报告路径")


class BugTrackerTool(BaseTool):
    name: str = "Bug ID 增量跟踪器"
    description: str = (
        "跟踪已分析过的 Bug ID，支持增量过滤（跳过已分析且状态未变的 Bug）、"
        "标记分析完成、查看统计。避免重复分析同一问题。"
    )
    args_schema: type[BaseModel] = BugTrackerInput

    def _run(self, action: str = "filter", bug_id: str = "",
             status: str = "", report_path: str = "") -> str:
        tracking = self._load()

        if action == "filter":
            return json.dumps(tracking, ensure_ascii=False, indent=2)

        elif action == "mark":
            tracking["bugs"][bug_id] = {
                "status": status,
                "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "report": report_path,
            }
            tracking["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._save(tracking)
            return f"Marked {bug_id} as analyzed (status={status})"

        elif action == "stats":
            bugs = tracking.get("bugs", {})
            total = len(bugs)
            by_status = {}
            for v in bugs.values():
                s = v.get("status", "unknown")
                by_status[s] = by_status.get(s, 0) + 1
            return json.dumps({
                "total_tracked": total,
                "by_status": by_status,
                "last_run": tracking.get("last_run", "never"),
            }, ensure_ascii=False, indent=2)

        return f"Unknown action: {action}"

    # ── 供 Python 调用的增量过滤方法 ──

    @staticmethod
    def filter_new_and_changed(issues: list[dict],
                               key_field: str = "bug_id",
                               status_field: str = "status") -> dict:
        """过滤：返回 {new, changed, skipped} 三组问题"""
        tracking = BugTrackerTool._load_static()

        new_issues = []
        changed_issues = []
        skipped_issues = []

        for issue in issues:
            bid = issue.get(key_field, "")
            if not bid:
                new_issues.append(issue)
                continue

            if bid not in tracking.get("bugs", {}):
                new_issues.append(issue)
            else:
                old_status = tracking["bugs"][bid].get("status", "")
                new_status = issue.get(status_field, "")
                if old_status.lower() != new_status.lower():
                    changed_issues.append(issue)
                else:
                    skipped_issues.append(issue)

        return {
            "new": new_issues,
            "changed": changed_issues,
            "skipped": skipped_issues,
        }

    @staticmethod
    def mark_analyzed(bug_id: str, status: str, report_path: str = "",
                      source_file: str = ""):
        tracking = BugTrackerTool._load_static()
        tracking["bugs"][bug_id] = {
            "status": status,
            "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "report": report_path,
        }
        tracking["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if source_file:
            tracking["source_file"] = source_file
        BugTrackerTool._save_static(tracking)

    # ── 内部方法 ──

    @staticmethod
    def _load_static() -> dict:
        if TRACKING_FILE.exists():
            try:
                return json.loads(TRACKING_FILE.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"last_run": "", "source_file": "", "bugs": {}}

    @staticmethod
    def _save_static(data: dict):
        TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRACKING_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> dict:
        return self._load_static()

    def _save(self, data: dict):
        self._save_static(data)
