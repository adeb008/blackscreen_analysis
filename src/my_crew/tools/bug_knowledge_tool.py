"""Bug 知识库 — 闭环迭代，两个工作流共用

analyzed_bugs.json 结构:
{
  "_meta": {
    "last_run": "2026-05-09 15:00",
    "source_file": "Bug_0509.xlsx",
    "total_analyzed": 89,
    "category_trend": {"SAIL": {"total": 21, "fixed": 11, "trend": "↓收敛"}, ...},
    "module_heatmap": {"QNX": 23, "Android": 36, ...}
  },
  "bugs": {
    "BUG001": {
      "status": "Closed",
      "severity": "A",
      "module": "QNX",
      "title": "...",
      "assignee": "...",
      # 工作流一写入
      "category": "SAIL/safetymonitor",
      "fix_status": "已修复",
      "refined_at": "2026-05-09 12:00",
      # 工作流二写入
      "root_cause": "safetymonitor 75ms超时",
      "fix_method": "高通基线更新",
      "confidence": "高",
      "analysis_layer": "QNX",
      "analysis_report": "reports/BUG001_analysis.md",
      "analyzed_at": "2026-05-09 14:00"
    }
  }
}
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from my_crew.config import get_kb_path

TRACKING_FILE = get_kb_path()


class BugKnowledgeInput(BaseModel):
    action: str = Field(default="filter", description="filter | mark_refined | mark_analyzed | stats | trends")
    bug_id: str = Field(default="")
    # mark_refined 参数
    category: str = Field(default="")
    fix_status: str = Field(default="")
    # mark_analyzed 参数
    root_cause: str = Field(default="")
    fix_method: str = Field(default="")
    confidence: str = Field(default="")
    analysis_layer: str = Field(default="")
    analysis_report: str = Field(default="")
    # 可选
    status: str = Field(default="")
    severity: str = Field(default="")
    module: str = Field(default="")
    title: str = Field(default="")
    assignee: str = Field(default="")


class BugKnowledgeTool(BaseTool):
    name: str = "bug_knowledge_base"
    description: str = (
        "闭环知识库：记录每条 Bug 的分类（工作流一）和深度分析结果（工作流二），"
        "支持增量过滤、趋势统计和模块热力图。action: filter | mark_refined | "
        "mark_analyzed | stats | trends"
    )
    args_schema: type[BaseModel] = BugKnowledgeInput

    def _run(self, action: str = "filter", bug_id: str = "",
             category: str = "", fix_status: str = "",
             root_cause: str = "", fix_method: str = "",
             confidence: str = "", analysis_layer: str = "",
             analysis_report: str = "",
             status: str = "", severity: str = "",
             module: str = "", title: str = "", assignee: str = "") -> str:

        kb = load_kb()

        if action == "filter":
            return json.dumps(kb, ensure_ascii=False, indent=2)

        elif action == "mark_refined":
            # 工作流一：记录分类结果
            entry = kb["bugs"].get(bug_id, {})
            entry["category"] = category
            entry["fix_status"] = fix_status
            entry["refined_at"] = now()
            if status: entry["status"] = status
            if severity: entry["severity"] = severity
            if module: entry["module"] = module
            if title: entry["title"] = title
            if assignee: entry["assignee"] = assignee
            kb["bugs"][bug_id] = entry
            save_kb(kb)
            return f"Refined: {bug_id} → {category}"

        elif action == "mark_analyzed":
            # 工作流二：记录深度分析结果
            entry = kb["bugs"].get(bug_id, {})
            entry["root_cause"] = root_cause
            entry["fix_method"] = fix_method
            entry["confidence"] = confidence
            entry["analysis_layer"] = analysis_layer
            entry["analysis_report"] = analysis_report
            entry["analyzed_at"] = now()
            if status: entry["status"] = status
            if module: entry["module"] = module
            if title: entry["title"] = title
            kb["bugs"][bug_id] = entry
            save_kb(kb)
            return f"Analyzed: {bug_id} → {root_cause[:60]}"

        elif action == "stats":
            # 聚合统计
            return json.dumps(compute_stats(kb), ensure_ascii=False, indent=2)

        elif action == "trends":
            # 趋势 + 热力图
            return json.dumps(compute_trends(kb), ensure_ascii=False, indent=2)

        return f"Unknown action: {action}"

    # ── 静态方法 ──

    @staticmethod
    def _load_static() -> dict:
        return load_kb()

    @staticmethod
    def _save_static(kb: dict):
        save_kb(kb)

    @staticmethod
    def filter_new_and_changed(issues: list[dict],
                               key_field: str = "bug_id",
                               status_field: str = "status") -> dict:
        kb = load_kb()
        new, changed, skipped = [], [], []
        for issue in issues:
            bid = issue.get(key_field, "")
            if not bid:
                new.append(issue)
            elif bid not in kb.get("bugs", {}):
                new.append(issue)
            else:
                old_status = kb["bugs"][bid].get("status", "")
                if old_status.lower() != issue.get(status_field, "").lower():
                    changed.append(issue)
                else:
                    skipped.append(issue)
        return {"new": new, "changed": changed, "skipped": skipped}


# ── 底层 IO ──

def load_kb() -> dict:
    if TRACKING_FILE.exists():
        try:
            return json.loads(TRACKING_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"_meta": {"last_run": "", "source_file": "",
                       "total_analyzed": 0}, "bugs": {}}


def save_kb(kb: dict):
    TRACKING_FILE.parent.mkdir(parents=True, exist_ok=True)
    # 更新元信息
    bugs = kb.get("bugs", {})
    now_str = now()
    kb["_meta"]["last_run"] = now_str
    kb["_meta"]["total_analyzed"] = len(bugs)
    # 计算趋势
    kb["_meta"].update(compute_trends(kb))
    
    # 历史归档：本轮快照（供趋势图使用）
    snapshot = {
        "timestamp": now_str,
        "total": len(bugs),
        "categories": dict(sorted(Counter(
            b.get("category", "未分类") for b in bugs.values()
        ).items(), key=lambda x: -x[1])),
        "modules": dict(sorted(Counter(
            b.get("module", "未知") for b in bugs.values()
        ).items(), key=lambda x: -x[1])[:20]),
        "fix_status": dict(Counter(
            b.get("fix_status", "未知") for b in bugs.values()
        ).most_common()),
        "severity": dict(Counter(
            b.get("severity", "未知") for b in bugs.values()
        ).most_common()),
    }
    history = kb["_meta"].setdefault("run_history", [])
    history.append(snapshot)
    # 保留最近 50 轮
    if len(history) > 50:
        kb["_meta"]["run_history"] = history[-50:]
    
    TRACKING_FILE.write_text(
        json.dumps(kb, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def compute_stats(kb: dict) -> dict:
    bugs = kb.get("bugs", {})
    total = len(bugs)
    if total == 0:
        return {"total": 0}

    by_category = Counter(b.get("category", "未分类") for b in bugs.values())
    by_module = Counter(b.get("module", "未知") for b in bugs.values())
    by_status = Counter(b.get("status", "未知") for b in bugs.values())
    by_severity = Counter(b.get("severity", "未知") for b in bugs.values())
    by_layer = Counter(b.get("analysis_layer", "未分析") for b in bugs.values())

    analyzed = sum(1 for b in bugs.values() if b.get("analyzed_at"))
    high_conf = sum(1 for b in bugs.values() if b.get("confidence") == "高")

    return {
        "total": total,
        "analyzed_deep": analyzed,
        "high_confidence": high_conf,
        "by_category": dict(by_category.most_common()),
        "by_module": dict(by_module.most_common()),
        "by_status": dict(by_status.most_common()),
        "by_severity": dict(by_severity.most_common()),
        "by_layer": dict(by_layer.most_common()),
    }


def compute_trends(kb: dict) -> dict:
    bugs = kb.get("bugs", {})
    cat_counter = Counter()
    cat_fixed = defaultdict(int)
    mod_counter = Counter()

    for b in bugs.values():
        cat = b.get("category", "未分类")
        mod = b.get("module", "未知")
        cat_counter[cat] += 1
        if b.get("fix_status") == "已修复" or b.get("status", "").lower() in ("closed", "confirm"):
            cat_fixed[cat] += 1
        mod_counter[mod] += 1

    # 趋势 = 每个分类的修复率
    category_trend = {}
    for cat, total in cat_counter.most_common():
        fixed = cat_fixed.get(cat, 0)
        rate = fixed / total * 100 if total > 0 else 0
        if rate >= 80:
            trend = "✅ 收敛"
        elif rate >= 50:
            trend = "🔶 收敛中"
        else:
            trend = "🔴 需关注"
        category_trend[cat] = {"total": total, "fixed": fixed,
                                "fix_rate": round(rate, 1), "trend": trend}

    return {
        "category_trend": category_trend,
        "module_heatmap": dict(mod_counter.most_common(15)),
    }
