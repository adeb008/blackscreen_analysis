"""MyCrew — 黑卡闪问题分析双工作流"""

from os import getenv
from pathlib import Path

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent

from my_crew.tools.excel_issue_tool import ExcelIssueTool
from my_crew.tools.bug_knowledge_tool import BugKnowledgeTool
from my_crew.tools.log_download_tool import LogDownloadTool
from my_crew.tools.experience_knowledge_tool import ExperienceMatchTool, ExperienceUpdateTool
from my_crew.tools.design_lesson_tool import DesignLessonSaveTool, DesignLessonQueryTool
from my_crew.tools.read_tool import ReadTool


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

    def llm(self) -> LLM:
        return LLM(
            model=getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            provider="anthropic",
            api_key=getenv("DEEPSEEK_ANTHROPIC_API_KEY"),
            base_url=getenv("DEEPSEEK_ANTHROPIC_BASE_URL"),
            timeout=int(getenv("ANTHROPIC_TIMEOUT_SECONDS", "600")),
            max_tokens=int(getenv("ANTHROPIC_MAX_TOKENS", "1000000")),
        )

    # ── 工作流一 Agents ──

    @agent
    def data_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["data_analyst"],
            llm=self.llm(),
            tools=[ExcelIssueTool(), BugKnowledgeTool()],
            verbose=True,
        )

    @agent
    def issue_refiner(self) -> Agent:
        return Agent(
            config=self.agents_config["issue_refiner"],
            llm=self.llm(),
            tools=[ExperienceMatchTool(), ReadTool()],  # 只查不写，写入由 experience_saver 负责
            verbose=True,
        )

    @agent
    def experience_saver(self) -> Agent:
        return Agent(
            config=self.agents_config["experience_saver"],
            llm=self.llm(),
            tools=[ReadTool(), ExperienceUpdateTool()],  # 需要读取 classification_data.json，禁止模拟数据
            verbose=True,
        )

    @agent
    def report_writer(self) -> Agent:
        return Agent(
            config=self.agents_config["report_writer"],
            llm=self.llm(),
            tools=[
                ReadTool(),              # 读取中间文件，避免模型虚构 read 工具
                ExperienceMatchTool(),
                DesignLessonQueryTool(),   # 写入前先查重
                DesignLessonSaveTool(),    # 写入设计经验库
            ],
            verbose=True,
        )

    # ── 工作流二 Agents ──

    @agent
    def log_downloader(self) -> Agent:
        return Agent(
            config=self.agents_config["log_downloader"],
            llm=self.llm(),
            tools=[LogDownloadTool(), BugKnowledgeTool()],
            verbose=True,
        )

    @agent
    def log_analyzer_mcu(self) -> Agent:
        return Agent(
            config=self.agents_config["log_analyzer_mcu"],
            llm=self.llm(),
            verbose=True,
        )

    @agent
    def log_analyzer_qnx(self) -> Agent:
        return Agent(
            config=self.agents_config["log_analyzer_qnx"],
            llm=self.llm(),
            verbose=True,
        )

    @agent
    def log_analyzer_android(self) -> Agent:
        return Agent(
            config=self.agents_config["log_analyzer_android"],
            llm=self.llm(),
            verbose=True,
        )

    @agent
    def report_publisher(self) -> Agent:
        return Agent(
            config=self.agents_config["report_publisher"],
            llm=self.llm(),
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
    def experience_save_task(self) -> Task:
        return Task(
            config=self.tasks_config["experience_save_task"],
            output_file="outputs/experience_save_report.md",
        )

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
            agents=[self.data_analyst(), self.issue_refiner(), self.experience_saver(), self.report_writer()],
            tasks=[self.data_analysis_task(), self.issue_refinement_task(), self.experience_save_task(), self.report_task()],
            process=Process.sequential,
            verbose=True,
        )

    def analysis_only_crew(self) -> Crew:
        """仅执行数据分析，生成 classification_data.json"""
        return Crew(
            agents=[self.data_analyst()],
            tasks=[self.data_analysis_task()],
            process=Process.sequential,
            verbose=True,
        )

    def experience_only_crew(self) -> Crew:
        """仅执行经验库写入"""
        return Crew(
            agents=[self.experience_saver()],
            tasks=[self.experience_save_task()],
            process=Process.sequential,
            verbose=True,
        )

    def report_only_crew(self) -> Crew:
        """仅执行报告生成"""
        return Crew(
            agents=[self.report_writer()],
            tasks=[self.report_task()],
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
