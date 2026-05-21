---
name: black-screen-analysis
description: "黑卡闪问题智能分析工作流 — 一键运行：Excel→25类分类→LLM精校→报告→Obsidian同步"
version: 3.0.0
category: software-development
---

# 黑卡闪问题智能分析工作流

> 一个可直接运行的 CrewAI 多 Agent 分析系统。
> 把 Bug_*.xlsx 丢进 `black_screen_data/`，运行一条命令，得到完整五段式分析报告、分类看板、趋势热力图、Obsidian 笔记。

---

## 一键运行

```bash
cd D:/my_crew && uv run python -c "from my_crew.main import refine_complete; refine_complete()"
```

自动执行七步流水线：
1. 增量过滤（new=0 时短路跳过 CrewAI）
2. CrewAI 3Agent：25类分类 + LLM精校 + 经验提炼 + 质量门禁
3. LLM 批量精校："需人工判断" Bug 喂 DeepSeek 重新分类
4. 关键词自学习：提取新关键词→回写到分类规则（下次自动生效）
5. 完整附录：全量 Bug 清单拼接报告→report_refined_complete.md
6. 趋势报告：HTML 热力图+折线图→trend_heatmap_report.html
7. Obsidian 同步：28篇笔记→保险库

## 所有运行方式

```bash
# 最常用：完整流程
uv run python -c "from my_crew.main import refine_complete; refine_complete()"

# 基础版（不含后处理）
uv run python -c "from my_crew.main import refine; refine()"

# 单独步骤
uv run python scripts/llm_reclassify_manual.py --batch 10       # LLM 精校
uv run python scripts/trend_heatmap_report.py --open            # 趋势图
uv run python scripts/sync_to_obsidian.py                       # Obsidian 同步
uv run python scripts/json_to_dashboard.py --open              # 交互看板
```

## 前置条件

| 条件 | 说明 |
|------|------|
| Python 3.10+ + uv | `uv sync` 安装依赖 |
| DeepSeek API Key | `.env` 中 `DEEPSEEK_ANTHROPIC_API_KEY=sk-xxx` |
| Excel 文件 | `black_screen_data/Bug_*.xlsx`（Trinity 导出） |
| Obsidian 保险库 | `OBSIDIAN_VAULT_PATH` 环境变量（可选） |

## 增量模式

系统自动对比 `analyzed_bugs.json`，只处理新增和状态变更的 Bug。

| 场景 | 行为 |
|------|------|
| 新 Excel，全部未分析 | 全量处理：工具分类→LLM精校→报告 |
| 更新 Excel，新增8+变更24 | LLM 聚焦新增+变更，已分析只更新统计 |
| 相同 Excel，0新增0变更 | **短路跳过** CrewAI，只跑后处理 |

## 产出物（outputs/）

| 文件 | 用途 |
|------|------|
| `report_refined_complete.md` | **最终报告**（含完整 Bug 清单） |
| `classification_data.json` | 结构化分类数据（12字段/条） |
| `classification_dashboard.html` | 交互式看板（搜索/筛选/导出CSV） |
| `trend_heatmap_report.html` | 趋势+热力图 |
| `keywords_override.json` | 自学习关键词 |

## 关键文件

| 文件 | 职责 |
|------|------|
| `src/my_crew/main.py` | 入口，`refine_complete()` |
| `src/my_crew/crew.py` | 3 Agent + 2 Crew 定义 |
| `src/my_crew/config/tasks.yaml` | Task 描述（增量/短路/质量门禁） |
| `src/my_crew/config/agents.yaml` | Agent 角色定义 |
| `src/my_crew/tools/excel_issue_tool.py` | 25类加权分类引擎 |
| `src/my_crew/tools/bug_knowledge_tool.py` | 闭环知识库 |
| `src/my_crew/models.py` | 分类规则唯一制源 |

## 注意事项

- 项目 Python 环境用 `uv run python`，不要直接 `python`
- DeepSeek 不支持 `output_pydantic`，结构化输出用 Markdown 表格
- LLM 不擅长大规模罗列数据——完整 Bug 清单由 Python 后处理生成
- CrewAI 超时设置：`DEEPSEEK_TIMEOUT_SECONDS=600`
- 新增 Bug 少时 LLM 精校可跳过（增量模式自动聚焦）
