# 黑卡闪问题分析工作流 — 当前状态

> 更新: 2026-05-15 (周五) | 项目: D:\my_crew

---

## 2026-05-15 改动（工作流一强化 v2）

| 轮次 | 改动 | 文件 | 说明 |
|:--:|------|------|------|
| 1 | **闭环回写** | `tools/excel_issue_tool.py` | 新增 `_persist_to_kb()` — 分类后自动写 `analyzed_bugs.json`（含趋势+热力图） |
| 1 | **精简 task** | `config/tasks.yaml` | 两处嵌入 25 类列表（~30行×2）替换为一行引用，省 ~60% task token |
| 1 | **修正 Agent** | `config/agents.yaml` | data_analyst goal: 11类 → 25类细粒度 |
| 2 | **唯一制源** | `models.py` ← `excel_issue_tool.py` | FINE_GRAINED_RULES 迁入 models.py 为唯一定义源；CATEGORY_DEFINITIONS 自动派生 |
| 2 | **结构化传递** | `excel_issue_tool.py` + `tasks.yaml` | 新增 `json_output` → `outputs/classification_data.json`（12字段/条）；issue_refiner 精确引用 |
| 2 | **质量门禁 P2** | `tasks.yaml` | issue_refiner 计算精校变更率；report_writer 在变更率 >30% 时输出告警 |
| 3 | **完整 Bug 清单附录** | `scripts/generate_bug_list_appendix.py` + `main.py` | 后处理脚本从 JSON 自动生成 665 条完整清单（1186 行附录），拼接报告→`report_refined_complete.md`。LLM 专注分析推理，Python 做数据罗列 |
| 4 | **趋势与热力图系统** | `scripts/trend_heatmap_report.py` + `tools/bug_knowledge_tool.py` + `main.py` | KB 每轮自动归档历史快照（`_meta.run_history`，保留最近 50 轮）；生成 HTML 趋势看板：分类分布柱状图、修复状态、模块热力图、分类×修复状态热力图矩阵、历史折线趋势图 |
| 5 | **LLM 批量精校** | `scripts/llm_reclassify_manual.py` | 将 166 条"需人工判断"喂给 DeepSeek → 成功精校 139 条 → "需人工判断"从 25% 降到 **4%**（27/665）。置信度: 高+中占 60%。低置信度建议人工复核 |
| 6 | **关键词自学习 → 回写工具** | `models.py` + `scripts/learn_keywords_from_llm.py` + `main.py` | LLM精校结果→提取新关键词（240个）→写入 `keywords_override.json` → `models.py` 加载时自动合并到 FINE_GRAINED_RULES 的 weak 级别。下次 `ExcelIssueTool` 运行自动使用学习到的关键词，无需改源码 |
| 7 | **增量过滤短路** | `main.py` | 当 `new_count=0` 且 `changed_count=0` 时，跳过 CrewAI 3 Agent 处理（省 ~3 分钟 LLM 推理），直接执行后处理。所有入口（run/refine/refine_complete/download/full）均生效 |
| 8 | **Obsidian 对接** | `scripts/sync_to_obsidian.py` + `main.py` | 自动同步到 Obsidian 保险库（28 篇笔记）：概览笔记（总览+趋势+分布）、25 类分类笔记（含完整 Bug 清单+WiKiLink 导航）、趋势笔记（分类趋势+修复状态）。`refine_complete()` 最后一步自动执行 |
| 9 | **Analysis/Confirm 状态处理** | `tools/excel_issue_tool.py` + `tasks.yaml` | 工具 `_classify_fix_status` 新增：status=Analysis → "未修复（分析中）"，status=Confirm → "未修复（待确认）"。此前 11+10 条被错标"已修复"的 Analysis/Confirm 问题全部纠正。报告新增「待分析」和「待确认」独立章节，Analysis 自动桥接工作流二 |
| 10 | **增量焦点模式** | `tasks.yaml`(3处) | 三个 Agent 的 task 描述都加了增量指引：data_analyst 只详述新增+变更的 Bug（已分析只更新统计）；issue_refiner 只精校新增+变更（已分析保持原分类）；report_writer 经验提炼聚焦新发现模式。当 new+changed ≤ 10 条时逐条覆盖，>50 条时按分类聚合 |
| — | **架构图更新 v2.2** | `outputs/diagram_*.html` | 三张架构图同步刷新：俯瞰图（含增量过滤短路/后处理管道/关键词闭环/输出通道）、工作流一详情（含四闭环图解/精校前后对比）、数据闭环（含历史归档/输出通道/端到端时序） |
| — | **架构图 v3.0 双输入+领域反馈** | `outputs/diagram_architecture_v3_dual_input.html` + `outputs/diagram_classification_feedback.html` | 全新架构设计：①双输入场景（开发阶段Bug_*.xlsx + SOP售后SPI/KernelLog）→ ②文档完整性三要素评分 → ③25类分类→按7大领域分发 → ④动态分类注册表（LLM驱动列表自更新）→ ⑤领域反馈闭环改善设计

> **结果**: 工作流一完全闭环 — 分类 → 写 KB → 增量过滤生效 → JSON 结构化传递 → LLM 精校有精确数据源

---

## 已完成

### 架构设计
- [x] 需求与软件架构文档 → `docs/architecture.md`
- [x] 架构全景图 (8张Mermaid) → `docs/architecture_diagram.html`
- [x] 双工作流设计 (refinement + download_analysis)

### 基础工具
- [x] Excel 读取 + Actual Result 解析 (`ExcelIssueTool` / `log_download_tool.py`)
- [x] 闭环知识库 (`BugKnowledgeTool` → `analyzed_bugs.json`)
- [x] 增量过滤 (跳过已分析且状态未变的 Bug)
- [x] NAS UNC 路径权限检查 + 日志下载 (`LogDownloadTool`)
- [x] 3/4 个 Analysis 问题日志已下载到 `T1Q黑卡闪问题分析/`

### 数据
- [x] 旧版449条问题分析 → `deep_analysis_v2.md` (25类分类)
- [x] 新版90条问题分析 (含 Actual Result 列)

### 学习资料
- [x] SPI MCU 重启日志工具 (`D:\2-tools\SPI Tools\`) — 协议 + 116条原因码
- [x] 8255 E01 售后黑卡闪分析文档 (43个真实案例)
- [x] 售后分析链路: SPI日志 → Kernel时序 → QNX状态 → Android → ramdump

### CrewAI
- [x] 8个 Agent / 8个 Task (`agents.yaml` + `tasks.yaml`)
- [x] 双 Crew (`refinement_crew` + `download_analysis_crew`)
- [x] 增量过滤入口 (`uv run refine` / `download` / `full`)

---

## 二、待完成

| 优先级 | 事项 | 位置 |
|:--:|------|------|
| **P0** | 填写日志分析分层确认清单 | `docs/log_analysis_checklist.md` |
| **P0** | 按清单重做时间线分析工具 | `tools/timeline_analyzer.py` |
| **P0** | 细化 MCU/QNX/Android 三层分析规则 | 协同整理 |
| **P1** | 时间线工具嵌入工作流二 | `crew.py` + `tasks.yaml` |
| **P1** | 报告推送实现 | Agent: report_publisher |
| **P1** | 工作流超时优化 (上次 Task 2 超时) | — |
| **P2** | Trinity 系统对接 (网页爬虫→API) | Phase 5 |
| **P2** | Cron 定时触发 (每30分钟) | Phase 5 |
| **P2** | 日志下载端到端验证 (CrewAI框架内) | — |

---

## 三、下周重启路径

```
1. 打开 docs/log_analysis_checklist.md → 填写各层分析内容
2. 告诉我"填好了" → 我重做时间线工具
3. 时间线工具验证 → 嵌入工作流二
4. 端到端跑通: Excel → 增量过滤 → 下载 → 时间线分析 → 报告
```

---

## 四、关键文件索引

| 文件 | 说明 |
|------|------|
| `docs/architecture.md` | 架构设计文档 |
| `docs/architecture_diagram.html` | 8张Mermaid架构全景图 |
| `docs/log_analysis_checklist.md` | **日志分析确认清单 (待填写)** |
| `src/my_crew/tools/timeline_analyzer.py` | 时间线工具 (待重做) |
| `src/my_crew/tools/bug_knowledge_tool.py` | 闭环知识库 |
| `src/my_crew/tools/log_download_tool.py` | 日志下载 |
| `src/my_crew/tools/excel_issue_tool.py` | Excel 分析 |
| `src/my_crew/config/agents.yaml` | 8个Agent |
| `src/my_crew/config/tasks.yaml` | 8个Task |
| `src/my_crew/crew.py` | 双Crew定义 |
| `src/my_crew/main.py` | 入口 (refine/download/full) |
| `black_screen_data/deep_analysis_v2.md` | 449条分析报告 |
| `T1Q黑卡闪问题分析/` | 已下载的3组日志 |
| `knowledge/` | 学习资料 (售后文档 + 图片) |
