# 黑卡闪问题分析工作流 — 当前状态

> 更新: 2026-05-09 (周五) | 项目: D:\my_crew

---

## 一、已完成

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
