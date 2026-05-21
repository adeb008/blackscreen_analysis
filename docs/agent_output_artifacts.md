# 工作流一 Agent 产出物定义

> 版本: v1.0 | 日期: 2026-05-18
> 每个 Agent 完成其 Task 后，将输出写入 `outputs/` 目录的指定文件。

---

## 数据流概览

```
Excel → data_analyst → issue_refiner → report_writer → final report
          │                 │
          ├─ Markdown 摘要   ├─ 报告前三章 + 精校记录
          ├─ JSON 分类数据   │
          └─ KB 回写         └─ (不写文件，纯输出给 report_writer)
```

---

## Agent 1: data_analyst

### 输入
- `{excel_path}` — Bug_*.xlsx 文件
- `tracking_file` — analyzed_bugs.json 路径（KB 自动回写）
- `json_output` — 结构化数据文件路径

### 工具
- `ExcelIssueTool` — 读取 Excel → 25类分类 → 统计 → 输出
- `BugKnowledgeTool` — 知识库增量过滤 + 回写

### 输出文件

#### 1. `outputs/data_analysis_summary.md`
**用途:** 给人类读者 + issue_refiner 参考的结构化 Excel 分析摘要。

**内容清单（必须包含）：**
| # | 章节 | 说明 |
|---|------|------|
| 1 | 基本信息 | 文件路径、数据行数、增量过滤结果（新增/变更/跳过）、KB回写状态 |
| 2 | 字段映射 | 标准字段→Excel列名的对应关系表 |
| 3 | 字段缺失情况 | Top 10 缺失字段及缺失率 |
| 4 | Status/Severity/Module/Frequency 分布 | 分布表 |
| 5 | 25类根因分类统计 | 每类的 Bug 数、占比 |
| 6 | **各分类下所有 Bug 完整清单** | 按根因分类分组，每组一个表格，包含全部 Bug（BUG ID、Title、根因、修复方式、状态、匹配关键词） |
| 7 | 交叉统计表 | Module x Severity / Module x 根因 / 根因 x 修复状态 |
| 8 | 典型 Bug 样例 | 前 N 条样例（可选补充） |
| 9 | 后续 Agent 分析提示 | 方案B精校指引、报告结构建议 |

**格式:** Markdown

**容量:** 中等（~30-50KB）

---

#### 2. `outputs/classification_data.json`
**用途:** 供 issue_refiner 精确引用每条 Bug 的结构化数据，避免从 Markdown 推测。

**内容清单（每条记录 12 个字段）：**
| 字段 | 类型 | 来源 |
|------|------|------|
| bug_id | string | Excel Bug ID 列 |
| title | string | Excel Title 列 |
| status | string | Excel Status 列 |
| severity | string | Excel Severity 列 |
| module | string | Excel Module 列 |
| root_cause_category | string | 25类分类结果（方案A） |
| fix_status | string | 已修复/未修复/无法复现 |
| score | string | 方案A 匹配分数 |
| matched_keywords | string | 命中的关键词 |
| parsed_root_cause | string | 从 Comments/CA 提取的根因 |
| parsed_fix_method | string | 从 Comments/SS 提取的修复方式 |
| comments | string | 原始 Comments（首300字截断） |

**格式:** JSON 数组

**容量:** 每条 ~500 字节，N 条总计 ~300KB

---

#### 3. `black_screen_data/analyzed_bugs.json`（KB 回写）
**用途:** 闭环知识库持久化，下次运行时增量过滤。

**写回字段（工作流一）：**
- category (string) — 25类分类名称
- fix_status (string) — 已修复/未修复/无法复现
- status (string) — Excel 原始 Status
- severity (string) — 严重度
- module (string) — 模块
- title (string) — 标题
- refined_at (string) — 本次分析时间戳

**自动计算：**
- category_trend — 各类修复率 + 收敛趋势
- module_heatmap — 模块 Top 15 热力图

---

## Agent 2: issue_refiner

### 输入
- `data_analyst` 的完整 Markdown 摘要（`outputs/data_analysis_summary.md`）
- `outputs/classification_data.json`（精确结构化数据）

### 工具
无（纯 LLM 推理）

### 输出文件

#### `outputs/refined_chapters.md`
**用途:** 标准分析报告的前三章 + LLM 精校记录。

**内容清单（必须包含）：**
| # | 章节 | 说明 |
|---|------|------|
| 1 | **第一章：已修复的问题及原因** | 按 12 个大类分组，每个分组下 1 个完整 Bug 表格（**全部 Bug，不省略**） |
| 2 | **第二章：未修复/挂起的问题** | 完整 Bug 表格（全部 Bug，不省略） |
| 3 | **第三章：核心问题分类统计** | 精校后 25 类分布 + 占比 + 处理状态 + 无法复现率 |
| 4 | **方案B LLM精校记录** | 末尾附表，包含精校明细 + 变更率 + 质量门禁告警 |

**第一章表格列：** `| Bug ID | 问题现象 | 根因 | 修复方式 |`
**第二章表格列：** `| Bug ID | 状态 | 问题现象 | 当前卡点 |`
**第三章表格列：** `| 根因大类 | 数量 | 占比 | 处理状态 |`

**关键约束：**
- ⚠️ **完整清单**: 第一章+Bug表格必须是该分类下**全部Bug**，不能省略或只列"典型样例"
- ⚠️ **禁止引用**: 不允许出现"完整清单见XXX"等交叉引用
- ⚠️ **精确引用**: 使用 JSON 数据做分类参考，不从 Markdown 推测

---

## Agent 3: report_writer

### 输入
- issue_refiner 的输出（`outputs/refined_chapters.md`）
- 增量过滤统计（`{new_count}`, `{skipped_count}` 等）

### 工具
无（纯 LLM 推理）

### 输出文件

#### `outputs/report_refined.md`
**用途:** 最终《黑卡闪问题提炼分析报告》，可直接用于研发评审和管理层汇报。

**报告结构（严格五段式）：**
| 章节 | 内容 | 来源 |
|------|------|------|
| **头部** | 数据来源、状态说明、增量模式 | 模板参数 |
| **一、已修复的问题及原因** | 直接使用 issue_refiner 第一章（含完整Bug表格） | issue_refiner |
| **二、未修复/挂起的问题** | 直接使用 issue_refiner 第二章（含完整Bug表格） | issue_refiner |
| **三、核心问题分类统计** | 使用 issue_refiner 第三章 + 精校影响说明 | issue_refiner |
| **四、需要提炼的经验点** | P0-P3 四级提炼，≥3条必须提炼，关联具体 Bug ID | report_writer 自行推理 |
| **五、总结** | 修复收敛/残留风险/最大风险/最需改进/工具建设/精校影响 | report_writer 自行推理 |

**总结表维度：**
| 维度 | 说明 |
|------|------|
| 已修复 | 哪些大类基本收敛 |
| 未修复/卡点 | 残留风险 |
| 最大风险 | 影响面最大的问题 |
| 最需改进 | 流程/工具/架构改进项（含质量门禁告警） |
| 工具建设 | 工具链建议 |
| 精校影响 | 方案B LLM精校对分类的修正效果 |

**关键约束：**
- ⚠️ Bug表格必须是该分类下**全部Bug**，不允许省略
- ⚠️ 禁止"完整清单见XXX"引用，报告自包含
- ⚠️ 质量门禁：精校变更率 >30% 时追加告警

---

## 文件总览

| 文件 | 写入者 | 读取者 | 核心数据 |
|------|:------:|:------:|----------|
| `outputs/data_analysis_summary.md` | data_analyst | issue_refiner, 人类 | Excel 全量分析 + 25类分类结果 |
| `outputs/classification_data.json` | data_analyst | issue_refiner | 每条Bug的12字段精确结构数据 |
| `black_screen_data/analyzed_bugs.json` | data_analyst | _incremental_filter (下次) | 闭环知识库 + 趋势 |
| `outputs/refined_chapters.md` | issue_refiner | report_writer | 报告前三章 + 精校记录 |
| `outputs/report_refined.md` | report_writer | 人类 | 五段式最终报告 |
