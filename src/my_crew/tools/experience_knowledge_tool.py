"""
ExperienceKnowledgeTool — CrewAI 工具
供 issue_refiner agent 在精校时调用，读取经验库 top3 作为上下文。
也供 report_writer 在写报告时补充经验。
"""
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from typing import Optional
import requests, os, json

API_BASE = os.environ.get("EXPERIENCE_API_URL", "http://10.219.9.92:8765")
API_KEY  = os.environ.get("EXPERIENCE_API_KEY", "")

def _headers():
    return {"X-API-Key": API_KEY} if API_KEY else {}


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
            resp = requests.post(
                f"{API_BASE}/match",
                json={"project": project, "bug_text": bug_text, "top_n": top_n},
                headers=_headers(),
                timeout=5
            )
            data = resp.json()
            if not data.get("results"):
                return "未找到相关历史经验。"
            lines = [f"找到 {data['count']} 条历史经验:"]
            for i, r in enumerate(data["results"], 1):
                lines.append(
                    f"{i}. [{r['category']}] 根因: {r['root_cause']} | "
                    f"解决方案: {r['solution']} | 置信度: {r['confidence']:.2f}"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"经验库查询失败: {e}"


class UpdateInput(BaseModel):
    project: str = Field(..., description="项目名称")
    category: str = Field(..., description="分类名称")
    summary: str = Field(..., description="经验摘要（一句话概括根因现象）")
    root_cause: str = Field(..., description="根因描述")
    solution: str = Field(..., description="解决方案")
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
             root_cause: str, solution: str, keywords: list,
             source_bug: str = "", confidence: float = 0.7) -> str:
        try:
            resp = requests.post(
                f"{API_BASE}/experience",
                json={
                    "project": project,
                    "category": category,
                    "summary": summary,
                    "root_cause": root_cause,
                    "solution": solution,
                    "keywords": keywords,
                    "source_bug": source_bug,
                    "confidence": confidence
                },
                headers=_headers(),
                timeout=5
            )
            data = resp.json()
            return f"经验库更新成功，experience_id={data['id']}"
        except Exception as e:
            return f"经验库更新失败: {e}"
