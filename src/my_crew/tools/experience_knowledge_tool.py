"""
ExperienceKnowledgeTool — CrewAI 工具
供 issue_refiner agent 在精校时调用，读取经验库 top3 作为上下文。
也供 report_writer 在写报告时补充经验。
"""
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
import requests, os, json, time

API_BASE = os.environ.get("EXPERIENCE_API_URL", "http://10.219.9.92:8765")
API_KEY  = os.environ.get("EXPERIENCE_API_KEY", "")
PROJECT_NAME = os.environ.get("PROJECT_NAME", "")

def _headers():
    return {"X-API-Key": API_KEY} if API_KEY else {}


def _fixed_project_name() -> str:
    return (PROJECT_NAME or "").strip()


def _red(msg: str) -> str:
    return f"\033[31m{msg}\033[0m"


class MatchInput(BaseModel):
    project: str = Field(..., description="项目名称，如 T1Q / T1G / ICI2")
    bug_text: str = Field(..., description="Bug 描述文本（标题+现象）")
    top_n: Optional[int] = Field(3, description="返回条数，默认3")


class ExperienceMatchTool(BaseTool):
    name: str = "experience_search"
    description: str = (
        "从黑卡闪经验库中检索与当前 Bug 最相关的历史经验，"
        "返回根因、解决方案和关键词，辅助分类精校。"
    )
    args_schema: type = MatchInput

    def _run(self, project: str, bug_text: str, top_n: int = 3) -> str:
        try:
            resolved_project = _fixed_project_name()
            if not resolved_project:
                return _red("经验库查询失败: .env 未配置 PROJECT_NAME")
            resp = requests.post(
                f"{API_BASE}/match",
                json={"project": resolved_project, "bug_text": bug_text, "top_n": top_n},
                headers=_headers(),
                timeout=5
            )
            try:
                data = resp.json()
            except ValueError:
                data = None
            if resp.status_code >= 400:
                detail = data.get("detail") if isinstance(data, dict) else (resp.text or "unknown error")
                return _red(f"经验库查询失败: HTTP {resp.status_code} - {detail}")
            if not isinstance(data, dict):
                return _red(f"经验库查询失败: 服务端返回非 JSON 响应: {resp.text[:200]}")
            if not data.get("results"):
                return "未找到相关历史经验。"
            lines = [f"找到 {data['count']} 条历史经验:"]
            if project != resolved_project:
                lines.insert(0, f"项目名强制使用 .env: {project} -> {resolved_project}")
            for i, r in enumerate(data["results"], 1):
                lines.append(
                    f"{i}. [{r['category']}] 根因: {r['root_cause']} | "
                    f"解决方案: {r['solution']} | 置信度: {r['confidence']:.2f}"
                )
            return "\n".join(lines)
        except Exception as e:
            return _red(f"经验库查询失败: {e}")


class UpdateInput(BaseModel):
    project: str = Field(..., description="项目名称")
    category: str = Field(..., description="分类名称")
    summary: str = Field(..., description="经验摘要（一句话概括根因现象）")
    root_cause: str = Field(..., description="根因描述")
    solution: Optional[str] = Field("", description="解决方案")
    keywords: list = Field(..., description="关键词列表")
    source_bug: Optional[str] = Field("", description="来源 Bug ID")
    confidence: Optional[float] = Field(0.7, description="置信度 0~1")


class ExperienceUpdateTool(BaseTool):
    name: str = "experience_update"
    description: str = (
        "将新识别的 Bug 分类经验写入经验库。"
        "LLM 精校后自动调用，实现经验库闭环更新。"
    )
    args_schema: type = UpdateInput

    def _run(self, project: str, category: str, summary: str,
             root_cause: str, solution: str = "", keywords: list = None,
             source_bug: str = "", confidence: float = 0.7) -> str:
        try:
            resolved_project = _fixed_project_name()
            if not resolved_project:
                return _red("经验库更新失败: .env 未配置 PROJECT_NAME")
            if keywords is None:
                keywords = []
            normalized_solution = (solution or "").strip()
            if not normalized_solution:
                if "需人工判断" in (category or ""):
                    normalized_solution = "待人工定位后补充修复方案"
                else:
                    normalized_solution = "待修复"
            payload = {
                "project": resolved_project,
                "category": category,
                "summary": summary,
                "root_cause": root_cause,
                "solution": normalized_solution,
                "keywords": keywords,
                "source_bug": source_bug,
                "confidence": confidence
            }
            resp = None
            max_attempts = 3
            for attempt in range(1, max_attempts + 1):
                resp = requests.post(
                    f"{API_BASE}/experience",
                    json=payload,
                    headers=_headers(),
                    timeout=5
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
                return _red(f"经验库更新失败: HTTP {resp.status_code} - {detail}")
            if not isinstance(data, dict):
                return _red(f"经验库更新失败: 服务端返回非 JSON 响应: {resp.text[:200]}")
            exp_id = data.get("id")
            if exp_id is None:
                return _red(f"经验库更新失败: 服务端返回缺少 id 字段(HTTP {resp.status_code}): {data}")
            schema = data.get("schema", "")
            status = data.get("status", "")
            return (
                "经验库更新成功: "
                f"id={exp_id}, schema={schema}, status={status}, "
                f"project={resolved_project}, category={category}, source_bug={source_bug or '-'}"
            )
        except Exception as e:
            return _red(f"经验库更新失败: {e}")
