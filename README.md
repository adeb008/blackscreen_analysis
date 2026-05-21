# 黑卡闪问题智能分析系统

> CrewAI 多 Agent 工作流：Excel 导出 → 25 类分类 → LLM 精校 → 经验提炼 → 完整报告 → Obsidian 同步

## 🚀 三步跑起来

```bash
# 1. 克隆
git clone <repo-url>
cd my_crew
uv sync

# 2. 配置 API Key
cp .env.example .env
# 编辑 .env，填入你的 DeepSeek API Key

# 3. 丢 Bug Excel 到 black_screen_data/
# 文件命名: Bug_*.xlsx（Trinity 导出）

# 运行！
uv run python -c "from my_crew.main import refine_complete; refine_complete()"
```

## 📊 产出物

运行后 `outputs/` 目录：

| 文件 | 说明 |
|------|------|
| `report_refined_complete.md` | 五段式分析报告 + 完整 Bug 清单附录 |
| `classification_data.json` | 结构化分类数据 |
| `classification_dashboard.html` | 交互式看板（搜索/筛选/CSV） |
| `trend_heatmap_report.html` | 趋势折线图 + 模块热力图 |
| `keywords_override.json` | LLM 自学习关键词 |

## 📁 项目结构

```
my_crew/
├── src/my_crew/
│   ├── config/          ← Agent/Task YAML 配置
│   ├── tools/           ← 分类引擎 + 知识库 + 日志工具
│   ├── crew.py          ← 3 Agent + 2 Crew
│   ├── main.py          ← 入口（refine / download / full）
│   ├── models.py        ← 25 类分类规则
│   └── config.py        ← 路径配置（自动检测）
├── scripts/             ← 后处理脚本
├── black_screen_data/   ← Bug Excel + 知识库
├── outputs/             ← 产物输出
├── docs/                ← 架构文档
├── .env.example         ← 环境变量模板
├── pyproject.toml       ← Python 项目配置
├── SKILL.md             ← Hermes/OpenClaw Agent Skill
└── README.md
```

## 🛠 前置条件

- Python 3.10+ / [uv](https://github.com/astral-sh/uv)
- DeepSeek API Key（`.env` 配置）
- Excel 文件（`Bug_*.xlsx`，Trinity 导出）
- Windows / Linux / macOS 均可

## 📖 详细文档

- 架构设计：[docs/architecture.md](docs/architecture.md)
- 架构图：[outputs/diagram_master_architecture.html](outputs/diagram_master_architecture.html)
- Agent 产出物：[docs/agent_output_artifacts.md](docs/agent_output_artifacts.md)

## 🤖 Hermes/OpenClaw Agent Skill

本项目附带 `SKILL.md`，可以直接加载到 Hermes 或 OpenClaw 中：

```
/skill black-screen-analysis
```

## ⚙️ 配置说明

| 环境变量 | 必需 | 默认值 |
|---------|:----:|------|
| `DEEPSEEK_ANTHROPIC_API_KEY` | ✅ | - |
| `DEEPSEEK_MODEL` | - | deepseek-v4-flash |
| `PROJECT_ROOT` | - | 自动检测 pyproject.toml 所在目录 |
| `OBSIDIAN_VAULT_PATH` | - | - |
| `NAS_MOUNT_PATH` | - | NAS 默认路径 |
