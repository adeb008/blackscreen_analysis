# my_crew 执行流程全景图

> v3.2 | 2026-05-27

---

## 总览

```
                     ┌─────────────────────────┐
                     │  uv run crewai run       │
                     │  refine_complete()       │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │  增量过滤 (_filtered)    │
                     │  对比 analyzed_bugs.json │
                     │  → new / changed / skip  │
                     └───────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │ 0条新增 → 短路    │ >0条 → 继续       │
              │ 跳过后处理       │                   │
              └──────────────────┘                   │
                                         ┌───────────▼───────────┐
                                         │  工作流一 CrewAI       │
                                         │  (3个Agent顺序执行)     │
                                         └───────────┬───────────┘
                                                     │
              ┌──────────────────────────────────────┼──────────────────────────────────────┐
              │                                      │                                      │
    ┌─────────▼─────────┐              ┌─────────────▼─────────────┐          ┌─────────────▼─────────────┐
    │ data_analyst      │              │ issue_refiner             │          │ report_writer              │
    │                   │──────────────▶                           │──────────▶                           │
    │ ExcelIssueTool    │              │ ExperienceMatchTool       │          │ ExperienceMatchTool        │
    │ BugKnowledgeTool  │              │ ExperienceUpdateTool      │          │                            │
    └───────────────────┘              └───────────────────────────┘          └─────────────────────────────┘
             │                                      │                                      │
             ▼                                      ▼                                      ▼
    outputs/                          outputs/                              outputs/
    classification_data.json          经验库回写                             report_refined.md
    analyzed_bugs.json                (服务器 10.219.9.92:8765)              
                                                     │
                                         ┌───────────▼───────────┐
                                         │  后处理链 (6步)        │
                                         │  refine_complete()     │
                                         └───────────┬───────────┘
                                                     │
         ┌──────────┬──────────┬──────────┬──────────┼──────────┬──────────┐
         │          │          │          │          │          │          │
    ┌────▼────┐┌───▼────┐┌───▼────┐┌───▼────┐┌───▼────┐┌───▼────┐┌───▼────┐
    │LLM精校  ││关键词  ││附录    ││趋势    ││Obsidian││经验库  ││新分类  │
    │需人工   ││自学习  ││拼接    ││热力图  ││同步    ││反哺    ││发现    │
    │判断     ││        ││        ││        ││28篇    ││        ││        │
    └─────────┘└────────┘└────────┘└────────┘└────────┘└────────┘└────────┘
```

---

## 一、入口方式

```bash
# 方式1: CrewAI 默认入口（工作流一）
uv run crewai run

# 方式2: Python 模块
uv run python -m my_crew.main refine           # 仅工作流一
uv run python -m my_crew.main download         # 仅工作流二(未完成)
uv run python -m my_crew.main full             # 双工作流串联

# 方式3: 完整闭环（推荐）
uv run python -c "from my_crew.main import refine_complete; refine_complete()"

# 强制全量重跑
set FORCE_FULL_RUN=1 && uv run crewai run
```

---

## 二、增量过滤 (_filtered_inputs)

```
Excel 最新 Bug_*.xlsx
        │
        ▼
  读取 all_bugs (673条)
        │
        ▼
  对比 analyzed_bugs.json (已分析记录)
        │
        ├── new_bugs:    KB中不存在的 Bug ID
        ├── changed:     KB中存在但 Status 变了
        └── skipped:     KB中存在且 Status 未变
        │
        ▼
  new=0 AND changed=0 → 短路（跳过CrewAI，直接后处理）
  否则 → 继续执行
```

短路时仍跑后处理（精校/附录/趋势/Obsidian），确保上次新增的问题也被精校。

---

## 三、工作流一 CrewAI（3个Agent顺序执行）

### Agent 1: data_analyst

| 项目 | 内容 |
|------|------|
| 工具 | ExcelIssueTool, BugKnowledgeTool |
| 输入 | Excel文件路径 |
| 输出 | 结构化分类摘要 (Markdown) |
| 核心 | **加权关键词匹配** → 25类分类 |

**ExcelIssueTool 内部流程：**
```
load_workbook(excel_path)
    │
    ▼
  映射列名 (column_aliases: Bug ID, Title, Comments, Cause Analysis, Solved Scheme)
    │
    ▼
  逐条: _build_analysis_text(record)
    │  只取 Title + Comments + Cause Analysis + Solved Scheme
    │  不含 Actual Result（那是工作流二的输入）
    │
    ▼
  _classify_weighted(text)
    │  FINE_GRAINED_RULES (28类)
    │  strong=3分, medium=2分, weak=1分
    │  exclude_keywords → 命中则跳过该类
    │  同分取 priority 高者
    │
    ▼
  输出字段:
    _root_cause_category   ← 分类名
    _root_cause_score      ← 匹配分数
    _root_cause_matched    ← 命中关键词
    _fix_status            ← 已修复/未修复/无法复现/分析中
    _parsed_root_cause     ← 从Comments/Cause Analysis提取的根因
    _parsed_fix_method     ← 从Solved Scheme提取的修复方案
    │
    ▼
  _persist_to_kb → analyzed_bugs.json
  _write_classification_json → classification_data.json (673条)
```

### Agent 2: issue_refiner

| 项目 | 内容 |
|------|------|
| 工具 | ExperienceMatchTool, ExperienceUpdateTool |
| 输入 | data_analyst 的分类结果 + classification_data.json |
| 输出 | 精校后的分类 + 分类统计 + 修正报告 |
| 核心 | **查经验库 → LLM精校 → 回写经验库** |

**三步精校：**
```
步骤1: ExperienceMatchTool("/match")
  → POST http://10.219.9.92:8765/match
  → 返回 top3 历史相似问题（项目+关键词匹配）
  
步骤2: LLM 推理
  → 结合数据源 analysis_text
  → 结合经验库 top3
  → 决定: 保持/修正/需人工判断
  
步骤3: ExperienceUpdateTool("/experience")
  → POST http://10.219.9.92:8765/experience
  → 回写本次精校结果到经验库
  → 命中已有经验 → hit_count+1, confidence+0.05
  → 新经验 → 新建记录
```

### Agent 3: report_writer

| 项目 | 内容 |
|------|------|
| 工具 | ExperienceMatchTool |
| 输入 | issue_refiner 的精校结果 |
| 输出 | outputs/report_refined.md |
| 核心 | **五段式报告 + 经验去重** |

**报告结构：**
```
第一章: 已修复的问题及原因（按根因大类分组）
第二章: 未修复/挂起的问题
第三章: 核心问题分类统计（含占比、趋势）
第四章: 经验沉淀与建议
第五章: 总结与后续计划
```

---

## 四、后处理链 (refine_complete 6步)

### Step 1: LLM 批量精校

```bash
uv run python scripts/llm_reclassify_manual.py --batch 10
```

- 读取 classification_data.json
- 筛选 `root_cause_category == "需人工判断"`
- 分批(10条/批)发送给 DeepSeek
- **Few-shot Prompting**: 自动注入 53条金标准案例
- LLM 返回精校后的分类 + 置信度 + 新分类建议
- 写回 classification_data.json + analyzed_bugs.json

**输出格式（5-6列）：**
```
精校模式: | Bug ID | 分类 | 置信度 | 判断依据 | 新分类建议 |
审查模式: | Bug ID | 现有分类 | 审查后分类 | 置信度 | 变更原因 | 新分类建议 |
```

### Step 2: 关键词自学习

```bash
uv run python scripts/learn_keywords_from_llm.py
```

- 从精校后的分类结果提取高频关键词
- 过滤垃圾词(NAS路径、日期戳、uidq用户名)
- 写入 `outputs/keywords_override.json`
- models.py 启动时自动加载到 FINE_GRAINED_RULES (weak级别)

### Step 3: 完整Bug清单附录

```bash
uv run python scripts/generate_bug_list_appendix.py
```

- 从 classification_data.json 读取全量673条
- 生成25类 × 每类全量Bug清单的Markdown附录
- 拼接到 report_refined.md → report_refined_complete.md
- 原则: Python做数据罗列，LLM做分析推理

### Step 4: 趋势热力图

```bash
uv run python scripts/trend_heatmap_report.py
```

- 读取 analyzed_bugs.json 的历史快照(保留50轮)
- 生成 HTML 交互看板(分类趋势折线图 + 模块热力图)
- 支持跨轮次对比

### Step 5: Obsidian同步

```bash
uv run python scripts/sync_to_obsidian.py
```

- 同步到 `D:\uidq1474\My Documents\Obsidian Vault\黑卡闪专项课题\`
- 28篇笔记: 1概览 + 25分类 + 2趋势
- 每篇含 YAML frontmatter + wikilink + Bug表格

### Step 6: 经验库关键词反哺

```bash
uv run python scripts/export_exp_keywords.py --min-confidence 0.7 --min-hits 2
```

- 从服务器 experience.db 导出高置信度关键词
- 写入 keywords_override.json
- 实现: 经验库 → 本地分类引擎 的闭环

---

## 五、动态分类扩展机制

```
LLM 精校时
    │
    ├── 发现新模式 ──→ 在"新分类建议"列填写
    │       │
    │       ▼
    │  outputs/pending_categories.json
    │       │
    │       ▼
    │  merge_new_categories.py (人工确认)
    │       │
    │       ├──→ models.py FINE_GRAINED_RULES (25→28→N)
    │       └──→ POST /rules → 服务器 experience.db
    │
    └── 现有分类可覆盖 ──→ 直接精校
```

---

## 六、服务器经验库架构

```
┌─────────────────────────────────────────────┐
│  服务器: 10.219.9.92:8765 (FastAPI)          │
│  DB: experience.db (SQLite, WAL模式)         │
│                                             │
│  表结构:                                     │
│    experiences     — 分类经验                │
│    feedback        — 人工纠正记录            │
│    project_stats   — 项目统计                │
│    category_rules  — 28类规则 (v2.0新增)     │
│                                             │
│  API:                                       │
│    GET  /health       — 健康检查+规则数       │
│    GET  /rules        — 获取28类完整规则      │
│    POST /rules        — 新增/更新分类规则     │
│    POST /match        — 关键词匹配历史经验    │
│    POST /experience   — 写入经验             │
│    POST /feedback     — 人工纠正             │
│    GET  /stats        — 项目统计             │
└─────────────────────────────────────────────┘
         ▲                    ▲
         │                    │
    ┌────┴────┐         ┌────┴────┐
    │ 本地引擎 │         │ 本地引擎 │
    │ 小王     │         │ 老张     │
    │ git pull │         │ git pull │
    └─────────┘         └─────────┘
```

---

## 七、关键数据流

```
输入层:
  Bug_*.xlsx (问题清单)  ──→  673条
  
分类层:
  FINE_GRAINED_RULES (28类)  ──→  weighted matching  ──→  分类结果
  
精校层:
  LLM (DeepSeek) + Few-shot  ──→  纠正误分类  ──→  新分类发现
  
知识层:
  analyzed_bugs.json (本地)  ←──→  experience.db (服务器)
  
输出层:
  classification_data.json  ──→  report_refined_complete.md
                             ──→  trend_heatmap_report.html
                             ──→  Obsidian Vault (28篇)
```

---

## 八、文件地图

```
my_crew/
├── src/my_crew/
│   ├── main.py                  ← 入口: refine()/refine_complete()/download()
│   ├── crew.py                  ← Agent/Task定义 + 工具挂载
│   ├── models.py                ← 28类规则定义 (FINE_GRAINED_RULES)
│   ├── config.py                ← 路径自动检测
│   ├── config/
│   │   ├── agents.yaml          ← Agent角色+目标描述
│   │   └── tasks.yaml           ← Task详细指令
│   └── tools/
│       ├── excel_issue_tool.py  ← Excel读取→25类加权分类
│       ├── bug_knowledge_tool.py← analyzed_bugs.json管理
│       ├── experience_knowledge_tool.py ← 服务器API(查/写)
│       └── log_download_tool.py ← 日志下载(工作流二)
│
├── scripts/
│   ├── llm_reclassify_manual.py ← LLM批量精校+新分类发现
│   ├── learn_keywords_from_llm.py ← 关键词自学习
│   ├── generate_bug_list_appendix.py ← 附录拼接
│   ├── trend_heatmap_report.py  ← 趋势HTML报告
│   ├── sync_to_obsidian.py      ← Obsidian同步
│   ├── extract_golden.py        ← 金标准提取
│   └── merge_new_categories.py  ← 新分类合并到规则库
│
├── docs/
│   └── workflow1-deployment-guide.md ← 部署指南
│
├── outputs/
│   ├── classification_data.json ← 673条结构化分类
│   ├── report_refined.md        ← LLM生成的5段式报告
│   ├── report_refined_complete.md ← 拼接完整Bug清单后
│   ├── trend_heatmap_report.html ← 趋势看板
│   ├── golden_examples.json     ← 53条金标准案例
│   ├── pending_categories.json  ← 待确认新分类
│   └── keywords_override.json   ← 自学习关键词
│
└── black_screen_data/
    ├── Bug_*.xlsx               ← 原始数据
    └── analyzed_bugs.json       ← 已分析Bug跟踪
```
