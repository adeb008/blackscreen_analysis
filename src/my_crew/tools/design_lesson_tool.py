"""
design_lesson_tool.py — 设计经验库工具（本地 Agent 调用）

report_writer Agent 使用此工具将提炼出的设计经验写入服务器经验库，
并可查询已有经验，避免重复写入。
"""
import os
import json
import time
import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional, List

DESIGN_API = os.getenv("EXPERIENCE_API_URL", "http://10.219.9.92:8765")
API_KEY    = os.getenv("EXPERIENCE_API_KEY", "")
PROJECT_NAME = os.getenv("PROJECT_NAME", "")
TIMEOUT = 10

def _headers():
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _red(msg: str) -> str:
    return f"\033[31m{msg}\033[0m"


# ─── 写入设计经验 ─────────────────────────────────────────────────────────────

class DesignLessonSaveInput(BaseModel):
    lesson_title: str = Field(..., description="经验标题，简洁描述这条设计教训，如「SAIL超时未设置看门狗兜底导致黑屏」")
    design_suggestion: str = Field(..., description="设计建议，这是核心字段，必须包含可操作的改进方向")
    project: Optional[str] = Field("", description="项目名称，如 8255_PJT / 8775_PJT")
    version: Optional[str] = Field("", description="软件版本号")
    phenomenon: Optional[str] = Field("", description="故障现象描述")
    root_cause: Optional[str] = Field("", description="根因分析结论")
    arch_module: Optional[str] = Field("", description="关联架构模块，自由文本，如 QNX/SAIL / Android/SurfaceFlinger / MCU/Watchdog")
    arch_layer: Optional[str] = Field("", description="架构层次: MCU / QNX / Android / 跨层")
    arch_doc_url: Optional[str] = Field("", description="飞书架构文档链接（可选，后续对接飞书时填写）")
    priority: Optional[str] = Field("P2", description="优先级: P0(必须立即整改) / P1(高优) / P2(中等) / P3(低优)")
    source_bug_ids: Optional[List[str]] = Field([], description="来源 Bug ID 列表，如 [\"BUG-001\", \"BUG-008\"]")


class DesignLessonSaveTool(BaseTool):
    name: str = "design_lesson_save"
    description: str = (
        "将报告中提炼出的设计经验写入服务器设计经验库（design_knowledge.db）。"
        "每一条独立的设计建议都应单独调用一次，不要合并多条经验为一次调用。"
        "lesson_title 和 design_suggestion 是必填项。"
    )
    args_schema: type = DesignLessonSaveInput

    def _run(
        self,
        lesson_title: str,
        design_suggestion: str,
        project: str = "",
        version: str = "",
        phenomenon: str = "",
        root_cause: str = "",
        arch_module: str = "",
        arch_layer: str = "",
        arch_doc_url: str = "",
        priority: str = "P2",
        source_bug_ids: List[str] = None,
    ) -> str:
        fixed_project = (PROJECT_NAME or "").strip()
        if not fixed_project:
            return _red("[design_lesson_save] 写入失败: .env 未配置 PROJECT_NAME")
        title_raw = (lesson_title or "").strip()
        if not title_raw:
            return _red("[design_lesson_save] 写入失败: lesson_title 为空")
        payload = {
            "lesson_title": title_raw,
            "design_suggestion": design_suggestion,
            "project": fixed_project,
            "version": version,
            "phenomenon": phenomenon,
            "root_cause": root_cause,
            "arch_module": arch_module,
            "arch_layer": arch_layer,
            "arch_doc_url": arch_doc_url,
            "priority": priority,
            "source_bug_ids": source_bug_ids or [],
        }
        try:
            resp = None
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                resp = requests.post(
                    f"{DESIGN_API}/design-lessons",
                    json=payload,
                    headers=_headers(),
                    timeout=TIMEOUT
                )
                if resp.status_code < 500 or attempt == max_attempts:
                    break
                time.sleep(0.5 * attempt)
            try:
                data = resp.json()
            except ValueError:
                data = None
            if resp.status_code >= 400:
                detail = data.get("detail") if isinstance(data, dict) else (resp.text or "unknown error")
                return _red(f"[design_lesson_save] 写入失败: HTTP {resp.status_code} - {detail}")
            if not isinstance(data, dict):
                return _red(f"[design_lesson_save] 写入失败: 服务端返回非 JSON 响应: {resp.text[:200]}")
            lesson_id = data.get("id")
            if lesson_id is None:
                return _red(f"[design_lesson_save] 写入失败: 服务端返回缺少 id 字段(HTTP {resp.status_code}): {data}")
            schema = data.get("schema", "")
            status = data.get("status", "")
            # 写后回查：确保目标标题在固定 project 下可查询到
            verify_resp = requests.get(
                f"{DESIGN_API}/design-lessons",
                params={"project": fixed_project, "limit": 500},
                headers=_headers(),
                timeout=TIMEOUT
            )
            try:
                verify_data = verify_resp.json()
            except ValueError:
                verify_data = None
            if verify_resp.status_code >= 400:
                detail = verify_data.get("detail") if isinstance(verify_data, dict) else (verify_resp.text or "unknown error")
                return _red(
                    "[design_lesson_save] 写入后校验失败: "
                    f"HTTP {verify_resp.status_code} - {detail}; id={lesson_id}, schema={schema}, title={title_raw}"
                )
            if not isinstance(verify_data, dict):
                return _red(
                    "[design_lesson_save] 写入后校验失败: 服务端返回非 JSON; "
                    f"id={lesson_id}, schema={schema}, title={title_raw}"
                )
            lessons = verify_data.get("lessons", []) or []
            found = any((l.get("lesson_title") or "").strip() == title_raw for l in lessons if isinstance(l, dict))
            if not found:
                return _red(
                    "[design_lesson_save] 写入后校验失败: 未在服务端列表中找到精确标题; "
                    f"id={lesson_id}, schema={schema}, project={fixed_project}, title={title_raw}"
                )
            return (
                "[design_lesson_save] 写入成功: "
                f"id={lesson_id}, schema={schema}, status={status}, "
                f"project={fixed_project}, priority={priority}, title={title_raw}"
            )
        except requests.RequestException as e:
            return _red(f"[design_lesson_save] 写入失败: {e}")


# ─── 查询设计经验（用于去重/参考） ──────────────────────────────────────────

class DesignLessonQueryInput(BaseModel):
    keyword: Optional[str] = Field("", description="关键词搜索（在标题/根因/建议中检索）")
    project: Optional[str] = Field("", description="按项目过滤")
    arch_layer: Optional[str] = Field("", description="按架构层过滤: MCU / QNX / Android / 跨层")
    priority: Optional[str] = Field("", description="按优先级过滤: P0 / P1 / P2 / P3")


class DesignLessonQueryTool(BaseTool):
    name: str = "design_lesson_query"
    description: str = (
        "查询服务器上已有的设计经验库。在写入新经验前可先查询是否已存在类似条目，"
        "避免重复。也可用于生成报告时参考历史经验。"
    )
    args_schema: type = DesignLessonQueryInput

    def _run(
        self,
        keyword: str = "",
        project: str = "",
        arch_layer: str = "",
        priority: str = "",
    ) -> str:
        try:
            fixed_project = (PROJECT_NAME or "").strip()
            if not fixed_project:
                return _red("[design_lesson_query] 查询失败: .env 未配置 PROJECT_NAME")
            if keyword:
                resp = requests.get(
                    f"{DESIGN_API}/design-lessons/search",
                    params={"keyword": keyword, "limit": 10},
                    headers=_headers(),
                    timeout=TIMEOUT
                )
            else:
                params = {}
                params["project"] = fixed_project
                if arch_layer:
                    params["arch_layer"] = arch_layer
                if priority:
                    params["priority"] = priority
                params["limit"] = 20
                resp = requests.get(
                    f"{DESIGN_API}/design-lessons",
                    params=params,
                    headers=_headers(),
                    timeout=TIMEOUT
                )
            resp.raise_for_status()
            data = resp.json()
            count = data.get("count", 0)
            lessons = data.get("lessons", [])
            if not lessons:
                return "[design_lesson_query] 未找到匹配的设计经验"
            lines = [f"[design_lesson_query] 找到 {count} 条设计经验:"]
            for l in lessons[:10]:
                lines.append(
                    f"  [{l.get('priority','?')}] {l.get('lesson_title','')} "
                    f"| 层: {l.get('arch_layer','')} 模块: {l.get('arch_module','')} "
                    f"| 项目: {l.get('project','')} "
                    f"| 建议: {l.get('design_suggestion','')[:60]}..."
                )
            return "\n".join(lines)
        except requests.RequestException as e:
            return _red(f"[design_lesson_query] 查询失败: {e}")
