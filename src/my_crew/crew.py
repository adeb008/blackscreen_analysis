from os import getenv

from crewai import Agent, Crew, LLM, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent

from my_crew.tools.excel_issue_tool import ExcelIssueTool


@CrewBase
class MyCrew:
    """Black-card flash issue refinement analysis crew.

    Produces analysis reports matching the format of:
    `黑卡闪问题提炼分析.md` — 5-section structure with root cause
    classification, statistics, lessons, and summary.
    """

    agents: list[BaseAgent]
    tasks: list[Task]

    def deepseek_llm(self) -> LLM:
        api_key = getenv("DEEPSEEK_API_KEY") or getenv("DEEPSEEK_ANTHROPIC_API_KEY")
        return LLM(
            model=getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
            provider="deepseek",
            api_key=api_key,
            base_url=getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            timeout=int(getenv("DEEPSEEK_TIMEOUT_SECONDS", "600")),
        )

    @agent
    def data_analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["data_analyst"],
            llm=self.deepseek_llm(),
            tools=[ExcelIssueTool()],
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
            output_file="outputs/report.md",
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
        )
