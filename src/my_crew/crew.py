"""MyCrew — 黑卡闪问题分析双工作流"""

from os import getenv
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent

from my_crew.tools.excel_issue_tool import ExcelIssueTool
from my_crew.tools.bug_knowledge_tool import BugKnowledgeTool
from my_crew.tools.log_download_tool import LogDownloadTool


@CrewBase
class MyCrew:
    """黑卡闪问题分析 Crew:

    工作流一: 问题分析提炼 — 从 Excel 分类统计 + 生成五段式报告
    工作流二: Analysis 问题下载分析 — 下载日志 + 逐层分析 + 生成报告

    增量跟踪: 通过 analyzed_bugs.json 记录已分析 Bug，避免重复分析。
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    _incremental_stats: dict = {}

    # ── LLM ──

    def deepseek_llm(self) -> LLM:
        api_key = getenv("DEEPSEEK_API_KEY") or getenv("DEEPSEEK_ANTHROPIC_API_KEY")
        return LLM(
            model=getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            provider="deepseek",
            api_key=api_key,
            base_url=getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=int(getenv("DEEPSEEK_TIMEOUT_SECONDS", "600")),
        )

    # ── 工作流一 Agents ──

    @agent
    def data_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["data_analyst"],
            llm=self.deepseek_llm(),
            tools=[ExcelIssueTool(), BugKnowledgeTool()],
            verbose=True,
        )

    @agent
    def issue_refiner(self) -> Agent:
        return Agent(
            config=self.agents_config["issue_refiner"],
            llm=self.deepseek_llm(),
            verbose=True,
        )

    @agent
    def report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["report_writer"],
            llm=self.deepseek_llm(),
            verbose=True,
        )

    # ── 工作流二 Agents ──

    @agent
    def log_downloader(self) -> Agent:
        return Agent(
            config=self.agents_config["log_downloader"],
            llm=self.deepseek_llm(),
            tools=[LogDownloadTool(), BugKnowledgeTool()],
            verbose=True,
        )

    @agent
    def log_analyzer_mcu(self) -> Agent:
        return Agent(
            config=self.agents_config["log_analyzer_mcu"],
            llm=self.deepseek_llm(),
            verbose=True,
        )

    @agent
    def log_analyzer_qnx(self) -> Agent:
        return Agent(
            config=self.agents_config["log_analyzer_qnx"],
            llm=self.deepseek_llm(),
            verbose=True,
        )

    @agent
    def log_analyzer_android(self) -> Agent:
        return Agent(
            config=self.agents_config["log_analyzer_android"],
            llm=self.deepseek_llm(),
            verbose=True,
        )

    @agent
    def report_publisher(self) -> Agent:
        return Agent(
            config=self.agents_config["report_publisher"],
            llm=self.deepseek_llm(),
            verbose=True,
        )

    # ── 工作流一 Tasks ──

    @task
    def data_analysis_task(self) -> Task:
        return Task(config=self.tasks_config["data_analysis_task"])

    @task
    def issue_refinement_task(self) -> Task:
        return Task(config=self.tasks_config["issue_refinement_task"])

    @task
    def report_task(self) -> Task:
        return Task(
            config=self.tasks_config["report_task"],
            output_file="outputs/report_refined.md",
        )

    # ── 工作流二 Tasks ──

    @task
    def download_logs_task(self) -> Task:
        return Task(config=self.tasks_config["download_logs_task"])

    @task
    def analyze_mcu_task(self) -> Task:
        return Task(config=self.tasks_config["analyze_mcu_task"])

    @task
    def analyze_qnx_task(self) -> Task:
        return Task(config=self.tasks_config["analyze_qnx_task"])

    @task
    def analyze_android_task(self) -> Task:
        return Task(config=self.tasks_config["analyze_android_task"])

    @task
    def publish_report_task(self) -> Task:
        return Task(
            config=self.tasks_config["publish_report_task"],
            output_file="reports/analysis_report.md",
        )

    # ── Crew 定义 ──

    @crew
    def crew(self) -> Crew:
        """默认: 工作流一 — 问题分析提炼"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )

    def refinement_crew(self) -> Crew:
        """工作流一: 问题分析提炼"""
        return Crew(
            agents=[self.data_analyst(), self.issue_refiner(), self.report_writer()],
            tasks=[self.data_analysis_task(), self.issue_refinement_task(),
                   self.report_task()],
            process=Process.sequential,
            verbose=True,
        )

    def download_analysis_crew(self) -> Crew:
        """工作流二: Analysis 问题下载分析"""
        return Crew(
            agents=[self.log_downloader(), self.log_analyzer_mcu(),
                    self.log_analyzer_qnx(), self.log_analyzer_android(),
                    self.report_publisher()],
            tasks=[self.download_logs_task(), self.analyze_mcu_task(),
                   self.analyze_qnx_task(), self.analyze_android_task(),
                   self.publish_report_task()],
            process=Process.sequential,
            verbose=True,
        )
