# my_crew 执行流程——逐函数详解

> v3.2 | 2026-05-27 | 每个函数调用、每次文件读写、每次API请求

---

## 第一部分：入口与增量过滤

### 1.1 入口函数链路

```
命令行                                Python入口
───────────────────────────────────────────────────────────
uv run crewai run          ──→  main.run()
uv run python -m my_crew.main refine  ──→  main.refine()
refine_complete()          ──→  main.refine_complete()
```

**`refine_complete()` 是推荐的完整入口**，包含 CrewAI + 6步后处理 + 经验库反哺。

### 1.2 `_filtered_inputs(excel_path, force)` → (inputs_dict, is_up_to_date)

```
STEP 1: 检查全量模式
  if FORCE_FULL_RUN=1 或 --force 在命令行:
    跳过增量过滤，excel_path = 最新 Bug_*.xlsx
    返回 ({topic, excel_path, new_count=total, ...}, False)

STEP 2: 增量过滤
  path = excel_path 或 _find_latest_excel()
  filt = _incremental_filter(path)
  → 返回 {new: [...], changed: [...], skipped: [...], total: N}

STEP 3: 判断短路
  if new_count == 0 AND changed_count == 0:
    返回 (inputs, True)  ← 跳过 CrewAI
  else:
    返回 (inputs, False) ← 继续执行
```

### 1.3 `_incremental_filter(excel_path)` → filter_result

```python
# 每一步的详细操作:

1. load_workbook(excel_path, read_only=True, data_only=True)
   打开 Excel，只读模式，不计算公式

2. ws = wb[wb.sheetnames[0]]
   取第一个 sheet

3. rows = list(ws.iter_rows(values_only=True))
   headers = rows[0]  # 第一行是列名

4. 扫描 headers，找 Bug ID 列 和 Status 列:
   for i, h in enumerate(headers):
       hl = h.lower().replace(" ", "")
       if "bugid" in hl or "bug id" in hl:  bug_id_col = i
       if "status" in hl:                    status_col = i

5. 构建 issues 列表:
   for row in rows[1:]:  # 跳过表头
       bid = str(row[bug_id_col]).strip()
       st  = str(row[status_col]).strip()
       issues.append({"bug_id": bid, "status": st})

6. BugKnowledgeTool.filter_new_and_changed(issues):
   读取 analyzed_bugs.json (如果存在):
     kb = {"_meta": {...}, "bugs": {"BUG001": {category, status, ...}}}
   
   对比 logic:
     已分析 Bug IDs = kb["bugs"].keys()
     
     for issue in issues:
         if bug_id not in 已分析:
             → new_bugs
         elif status != kb["bugs"][bug_id]["status"]:
             → changed_bugs
         else:
             → skipped_bugs
   
   返回: {"new": [...], "changed": [...], "skipped": [...]}

7. 保存源文件信息:
   kb["_meta"]["source_file"] = Path(excel_path).name
   BugKnowledgeTool._save_static(kb)

8. result["total"] = len(issues)
   返回 result
```

### 1.4 BugKnowledgeTool 静态方法

```python
# 文件路径: black_screen_data/analyzed_bugs.json

@staticmethod
def _load_static() -> dict:
    if not KB_FILE.exists():
        return {"_meta": {}, "bugs": {}}
    return json.loads(KB_FILE.read_text(encoding="utf-8"))

@staticmethod  
def _save_static(kb: dict):
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_FILE.write_text(json.dumps(kb, ensure_ascii=False, indent=2))

@staticmethod
def filter_new_and_changed(issues: list[dict]) -> dict:
    kb = _load_static()
    known = set(kb.get("bugs", {}).keys())
    
    new, changed, skipped = [], [], []
    for issue in issues:
        bid = issue["bug_id"]
        if bid not in known:
            new.append(issue)
        elif issue["status"] != kb["bugs"][bid].get("status", ""):
            changed.append(issue)
        else:
            skipped.append(issue)
    
    return {"new": new, "changed": changed, "skipped": skipped}
```

---

## 第二部分：CrewAI 工作流一

### 2.1 整体架构

```
MyCrew().refinement_crew()
  │
  ├── Agent 1: data_analyst
  │     tools=[ExcelIssueTool(), BugKnowledgeTool()]
  │     task=data_analysis_task (来自 tasks.yaml)
  │     ↓ LLM决定如何调用工具
  │
  ├── Agent 2: issue_refiner  
  │     tools=[ExperienceMatchTool(), ExperienceUpdateTool()]
  │     task=issue_refinement_task
  │     ↓ LLM根据 data_analyst 的输出做精校
  │
  └── Agent 3: report_writer
        tools=[ExperienceMatchTool()]
        task=report_task
        ↓ 生成五段式报告
```

### 2.2 CrewAI 启动 (crew.py → refinement_crew)

```python
def refinement_crew(self) -> Crew:
    return Crew(
        agents=[
            self.data_analyst(),    # Agent配置来自 agents.yaml
            self.issue_refiner(),
            self.report_writer()
        ],
        tasks=[
            self.data_analysis_task(),     # Task配置来自 tasks.yaml
            self.issue_refinement_task(),
            self.report_task()
        ],
        process=Process.sequential,  # 顺序执行
        verbose=True
    )
```

**Agent 配置示例 (agents.yaml → data_analyst):**
```yaml
data_analyst:
  role: 黑卡闪问题数据分析师
  goal: >
    读取 Bug 清单 Excel，调用 Excel Black-Screen/Freeze/Flicker Issue Analyzer
    工具完成25类细粒度根因分类，输出结构化分类摘要
  backstory: >
    你擅长从 Excel 中提取字段映射、计算分布、做加权关键词匹配
    你只依赖工具的分类结果，不做主观判断
```

**Task 配置示例 (tasks.yaml → data_analysis_task):**
```yaml
data_analysis_task:
  description: >
    请运行 Excel Black-Screen/Freeze/Flicker Issue Analyzer 工具，
    参数: excel_path={excel_path}, tracking_file=black_screen_data/analyzed_bugs.json,
    json_output=outputs/classification_data.json
    增量模式: 新增 {new_count} 条, 变更 {changed_count} 条
  expected_output: >
    结构化分类摘要: 字段映射/分布/25类根因分类/修复状态/交叉表/典型样例
  agent: data_analyst
```

### 2.3 Agent 1: data_analyst 执行过程

```
LLM 收到 task description (含 excel_path, tracking_file, json_output 参数)
  │
  ▼
LLM 决定调用工具: ExcelIssueTool
  │
  ├── 参数1: excel_path="black_screen_data/Bug_20260521103307.xlsx"
  ├── 参数2: sheet_name=None (自动取第一个sheet)
  ├── 参数3: tracking_file="black_screen_data/analyzed_bugs.json"
  └── 参数4: json_output="outputs/classification_data.json"
  │
  ▼
ExcelIssueTool._run() 执行 — 见 2.4 节
  │
  ▼
返回结构化摘要 (Markdown 文本, 约 2000-3000 行)
  │
  ▼
LLM 再次调用 BugKnowledgeTool (action="filter")
  → 读取 analyzed_bugs.json 全量数据
  → 作为上下文传给下一个 Agent
```

### 2.4 ExcelIssueTool._run() 详细过程

```python
def _run(self, excel_path, sheet_name=None, max_examples=20,
         tracking_file=None, json_output=None) -> str:
    
    # ── 阶段1: 加载 Excel ──
    path = Path(excel_path)
    if not path.exists():
        return "Error: Excel file not found"
    
    workbook = load_workbook(path, read_only=True, data_only=True)
    # data_only=True: 不计算公式, 只读缓存值
    
    # 工作表选择 (大小写不敏感)
    worksheet = self._get_worksheet(workbook, sheet_name)
    # sheet_name=None → workbook.sheetnames[0] → "sheet1"
    # sheet_name="Sheet1" → lower匹配 → 找到 "sheet1"
    
    # ── 阶段2: 解析行列 ──
    rows = list(worksheet.iter_rows(values_only=True))
    headers = [self._clean_cell(v) or f"Unnamed Column {i+1}" 
               for i, v in enumerate(rows[0])]
    # _clean_cell: None→"", strip(), 移除换行
    
    records = self._records_from_rows(headers, rows[1:])
    # 每行 → dict: {列名: 单元格值}
    # 跳过全空行
    
    # ── 阶段3: 列名映射 ──
    mapping = self._map_columns(headers, records)
    # column_aliases: {"bug_id": ["bug id","bugid","id","缺陷id"],
    #                   "title": ["title","标题","问题标题"],
    #                   "comments": ["comments","备注","评论"],
    #                   "root_cause": ["root cause","根因","Cause Analysis"],
    #                   "solved_scheme": ["solved scheme","解决对策"],
    #                   "status": ["status","状态"],
    #                   ...}
    # 
    # 算法: 遍历 records 第一行, 对每个标准字段尝试匹配别名
    # 匹配规则: value.lower().replace(" ","") == alias.lower().replace(" ","")
    # 输出: {"bug_id": "Bug ID", "title": "Title", ...}

    # ── 阶段4: 逐条分类 (核心循环) ──
    for record in records:
        
        # 4a: 构建分析文本
        text = self._build_analysis_text(record, mapping)
        # 只取4列: Title + Comments + Cause Analysis + Solved Scheme
        # 不含 Actual Result (防止NAS路径/日志目录名污染)
        # 实际代码:
        #   source_keys = ["title", "comments", "root_cause", "solved_scheme"]
        #   for key in source_keys:
        #       col = mapping.get(key)
        #       if col and record.get(col):
        #           parts.append(record[col])
        #   return "\n".join(parts)
        
        # 4b: 加权关键词分类
        rc = self._classify_weighted(text)
        # 详见 2.4.1 节
        record["_root_cause_category"] = rc["category"]
        record["_root_cause_section"]  = rc["section"]
        record["_root_cause_score"]    = str(rc["score"])
        record["_root_cause_matched"]  = ", ".join(rc["matched_keywords"])
        
        # 4c: 提取根因和修复方式
        dedicated_rc = self._value(record, mapping.get("root_cause"))
        dedicated_solved = self._value(record, mapping.get("solved_scheme"))
        parsed = self._parse_comments(
            self._value(record, mapping.get("comments"))
        )
        record["_parsed_root_cause"] = dedicated_rc or parsed["root_cause"]
        record["_parsed_fix_method"] = dedicated_solved or parsed["fix_method"]
        # _parse_comments 支持格式:
        #   [root_cause]:xxx / [solution]:xxx
        #   根本原因:xxx / 解决对策:xxx
        
        # 4d: 判断修复状态
        record["_fix_status"] = self._classify_fix_status(record, mapping, text)
        # _classify_fix_status 逻辑:
        #   1. 检查 UNREPRODUCIBLE_WORDS → "无法复现"
        #   2. 检查 PENDING_STATUS_WORDS → "未修复/挂起"
        #   3. 检查 FIXED_STATUS_WORDS → "已修复"
        #   4. 检查 ANALYSIS_STATUS_WORDS → "未修复（分析中）"
        #   5. 检查 CONFIRM_STATUS_WORDS → "未修复（待确认）"
        #   6. fallback → "已修复"

    # ── 阶段5: 知识库回写 (闭环) ──
    if tracking_file:
        self._persist_to_kb(records, mapping, tracking_file, str(path))
        # 写入 analyzed_bugs.json:
        #   每条Bug: {category, fix_status, refined_at, status, severity, module, title}
        #   元信息: {last_run, source_file, total_analyzed, category_trend, module_heatmap}
        #   历史快照: run_history (保留50轮)

    # ── 阶段6: 结构化JSON输出 ──
    if json_output:
        self._write_classification_json(records, mapping, json_output)
        # 写入 outputs/classification_data.json:
        #   [{bug_id, title, status, severity, module,
        #     root_cause_category, fix_status, score, matched_keywords,
        #     parsed_root_cause, parsed_fix_method, comments}, ...]

    # ── 阶段7: 组装Markdown输出 ──
    lines = []
    lines.append("# 黑卡闪问题 Excel 结构化分析摘要（方案A+B）")
    lines.append(f"- 文件: {excel_path}")
    lines.append(f"- 数据行数: {len(records)}")
    
    # 字段映射
    lines.append("\n## 字段映射")
    for std_name in ["bug_id","title","comments",...]:
        lines.append(f"- {std_name}: {mapping.get(std_name) or '未识别'}")
    
    # 字段缺失
    lines.append("\n## 字段缺失情况")
    # 对每列 counter = Counter(1 for r in records if not r[col])
    
    # 标准分布
    self._append_distribution(lines, "Status 分布", records, mapping.get("status"))
    self._append_distribution(lines, "Severity 分布", records, mapping.get("severity"))
    self._append_distribution(lines, "Module 分布", records, mapping.get("module"))
    self._append_distribution(lines, "Frequency 分布", records, mapping.get("frequency"))
    # _append_distribution 算法:
    #   counter = Counter(r[col] for r in records)
    #   按数量降序输出

    # 根因分类统计
    lines.append("\n## 根因分类统计（25类细粒度）")
    rc_counter = Counter(r["_root_cause_category"] for r in records)
    for cat, count in rc_counter.most_common():
        lines.append(f"- {cat}: {count} ({count/len(records)*100:.1f}%)")

    # 修复状态分组
    lines.append("\n## 修复状态分组")
    fix_counter = Counter(r["_fix_status"] for r in records)
    for status, count in fix_counter.most_common():
        lines.append(f"- {status}: {count}")

    # 各根因大类Bug清单 (每类最多15条)
    lines.append("\n## 各根因大类 Bug 清单")
    bugs_by_cat = defaultdict(list)
    for record in records:
        bugs_by_cat[record["_root_cause_category"]].append(record)
    for cat, bug_list in sorted(bugs_by_cat, ...):
        lines.append(f"\n### {cat}（{len(bug_list)} 条）")
        for bug in bug_list[:15]:
            lines.append(f"  - [{bug_id}] {title}")
            lines.append(f"    - 根因: {root_cause[:200]}")
            lines.append(f"    - 修复: {fix_method[:200]}")

    # 交叉统计
    self._append_cross_table(lines, "Module x Severity", ...)
    self._append_cross_table(lines, "Module x 根因分类", ...)
    self._append_cross_table(lines, "根因分类 x 修复状态", ...)
    # _append_cross_table 算法:
    #   matrix = defaultdict(lambda: defaultdict(int))
    #   for r in records:
    #       matrix[r[row_field]][r[col_field]] += 1
    #   输出 Markdown 表格

    # 典型样例
    lines.append(f"\n## 典型问题样例（前 {max_examples} 条）")
    for i, record in enumerate(records[:max_examples], 1):
        lines.append(f"{i}. [{bug_id}] {title} | 根因分类={rc_cat} | ...")

    return "\n".join(lines)
```

### 2.4.1 `_classify_weighted(text)` — 核心分类算法

```python
def _classify_weighted(self, text: str) -> dict:
    text_lower = text.lower()
    best = {"category": "需人工判断", "section": "三、待分析", 
            "score": 0, "matched_keywords": []}

    for rule in FINE_GRAINED_RULES:  # 28类规则, 来自 models.py
        # ── 负向排除检查 ──
        excluded = False
        for ekw in rule.get("exclude_keywords", []):
            if ekw.lower() in text_lower:
                excluded = True
                break
        if excluded:
            continue  # 跳过这个分类
        
        # ── 加权计分 ──
        score = 0
        hits = []
        for strength, weight in [("strong", 3), ("medium", 2), ("weak", 1)]:
            for kw in rule["keywords"].get(strength, []):
                if kw.lower() in text_lower:
                    score += weight
                    hits.append(kw)
        
        if score == 0:
            continue
        
        # ── 比较：更高分胜出；同分取 priority 高者 ──
        if score > best["score"] or (
            score == best["score"] and rule["priority"] > best.get("_priority", 0)
        ):
            best = {"category": rule["name"], "section": rule["section"],
                    "score": score, "matched_keywords": hits,
                    "_priority": rule["priority"]}
        elif score == best["score"] and score > 0:
            best["conflict_hint"] = f"与「{rule['name']}」同分({score}分)"
    
    return best
```

**FINE_GRAINED_RULES 数据结构** (来自 models.py):
```python
FINE_GRAINED_RULES: list[dict] = [
    {
        "name": "硬件-显示屏/解串器",
        "description": "解串器 SerDes 异常、DSI/LVDS link down",
        "keywords": {
            "strong": ["解串器", "serdes", "dsi", "lvds", "掉link", "link down"],
            "medium": ["显示屏", "屏线束", "寄存器", "mipi"],
            "weak": ["屏幕", "panel", "display"],
        },
        "exclude_keywords": [],
        "priority": 85,
        "section": "一、已修复的问题及原因",
    },
    # ... 共28条
]
# models.py 启动时还自动合并 keywords_override.json:
#   if _OVERRIDE_PATH.exists():
#       for cat, kws in _overrides.items():
#           _rule_map[cat]["keywords"]["weak"].extend(kws)
```

### 2.5 Agent 2: issue_refiner 执行过程

```
LLM 收到: data_analyst 的输出 (分类摘要 + Bug清单) + task描述
  │
  ▼
步骤1: ExperienceMatchTool (经验库检索)
  │  POST http://10.219.9.92:8765/match
  │  Body: {"project": "T1Q", "bug_text": "标题+现象描述", "top_n": 3}
  │
  │  服务器端 match_experience(project, bug_text, top_n):
  │    SELECT * FROM experiences WHERE project=? OR project='ALL'
  │    ORDER BY hit_count * confidence DESC LIMIT 50
  │    → 逐条关键词匹配 → 打分 → 排序 → 返回 top_n
  │
  │  返回: {count: 3, results: [
  │    {category, root_cause, solution, keywords, confidence, ...},
  │    ...
  │  ]}
  │
  ▼
步骤2: LLM 精校推理
  │  输入:
  │    - data_analyst 的分类结果 (每条的 _root_cause_category)
  │    - classification_data.json (结构化数据)
  │    - 经验库 top3 (历史相似问题)
  │
  │  LLM 判断:
  │    - 经验库匹配 → 与历史保持一致或提出更优分类
  │    - 冲突 → 分析后决定
  │    - 无匹配 → 自主判断
  │
  ▼
步骤3: ExperienceUpdateTool (回写经验库)
  │  POST http://10.219.9.92:8765/experience
  │  Body: {
  │    "project": "T1Q",
  │    "category": "硬件-显示屏/解串器",
  │    "root_cause": "MIPI信号中断", 
  │    "solution": "检查MIPI时序",
  │    "keywords": ["黑屏", "MIPI", "主屏"],
  │    "source_bug": "BUG20260513_06373",
  │    "confidence": 0.8
  │  }
  │
  │  服务器端 upsert_experience():
  │    同项目+分类+根因已存在 → hit_count+1, confidence+0.05
  │    不存在 → INSERT 新记录
  │    → 同时更新 project_stats
  │
  ▼
输出: 精校后分类 + 修正报告 + 分类统计
```

### 2.6 Agent 3: report_writer 执行过程

```
LLM 收到: issue_refiner 的精校结果 + task描述
  │
  ▼
步骤1: ExperienceMatchTool (经验去重)
  │  对每个 Bug 检索经验库
  │  已有经验 → 引用不重复详述
  │  新发现 → 展开分析
  │
  ▼
步骤2: 生成五段式报告
  │
  ├── 第一章: 已修复的问题及原因
  │    按根因大类分组, 每类下Bug列表
  │    格式: | Bug ID | 标题 | 根因 | 修复方式 | 修复状态 |
  │
  ├── 第二章: 未修复/挂起的问题
  │    同格式, 按紧急程度排序
  │
  ├── 第三章: 核心问题分类统计
  │    每个分类的Bug数量 + 修复率 + 趋势
  │    格式: | 分类 | 总数 | 已修复 | 修复率 | 趋势 |
  │
  ├── 第四章: 经验沉淀与建议
  │    高频问题模式总结
  │    新发现的问题类型
  │    建议关注方向
  │
  └── 第五章: 总结与后续计划
  │
  ▼
写入 outputs/report_refined.md
```

---

## 第三部分：后处理链 (refine_complete 的6步)

### 3.1 Step 1: LLM 批量精校

```bash
# 实际调用:
uv run python scripts/llm_reclassify_manual.py --batch 10
```

**详细流程:**

```
1. main() 入口
   │
   ├── 读取 outputs/classification_data.json (673条, 每条约15字段)
   │
   ├── 筛选 target_bugs:
   │   if --all:
   │       target_bugs = all_bugs (审查模式, 审查已有分类)
   │       use_review_mode = True
   │   else:
   │       target_bugs = [b for b in all_bugs if b["root_cause_category"] == "需人工判断"]
   │       use_review_mode = False
   │
   ├── 分批: batches = [target_bugs[i:i+10] for i in range(0, total, 10)]
   │
   ├── 逐批调用 LLM:
   │   for i, batch in enumerate(batches, 1):
   │       if use_review_mode:
   │           resp = call_deepseek_review(batch, i, total_batches)
   │       else:
   │           resp = call_deepseek(batch, i, total_batches)
   │       
   │       results = parse_response(resp, is_review=use_review_mode)
   │       all_results.update(results)
   │
   │   # call_deepseek 内部:
   │   #   构建 user_msg (每条Bug: Bug ID + Title + Comments + RootCause + Keywords)
   │   #   system_prompt = SYSTEM_PROMPT (含Few-shot金标准案例 + 28类定义)
   │   #   POST DeepSeek API (temperature=0.1, max_tokens=2000, timeout=300)
   │   #   失败自动重试3次, 间隔20/40/60秒
   │
   │   # parse_response 内部:
   │   #   按 | 分割Markdown表格行
   │   #   review模式: BugID|现有分类|审查后分类|置信度|变更原因|新分类建议
   │   #   精校模式: BugID|分类|置信度|判断依据|新分类建议
   │   #   返回 {bug_id: {category, confidence, reason, new_category}}
   │
   ├── 收集新分类建议:
   │   for bid, info in all_results.items():
   │       nc = info.get("new_category", "").strip()
   │       if nc and nc != "需人工判断":
   │           new_cats[nc].append(bid)
   │   
   │   写入 outputs/pending_categories.json:
   │     {"系统-UI/弹窗": ["BUG001", "BUG002"], ...}
   │
   ├── 写回 classification_data.json:
   │   for bug in all_bugs:
   │       if bug["bug_id"] in all_results:
   │           info = all_results[bug["bug_id"]]
   │           if info["category"] != bug.get("category_before_refine"):
   │               bug["root_cause_category"] = info["category"]
   │               bug["refined_confidence"] = info["confidence"]
   │               changed += 1
   │
   └── 写回 analyzed_bugs.json:
       for bug_id, info in all_results.items():
           kb["bugs"][bug_id]["category"] = info["category"]
           kb["bugs"][bug_id]["refined_at"] = now
       
       重新计算 category_trend + module_heatmap
       追加 run_history 快照
```

### 3.2 Step 2: 关键词自学习

```bash
uv run python scripts/learn_keywords_from_llm.py
```

```
1. 读取 classification_data.json (精校后)
2. 按分类聚合Bug:
   {category: [bug1, bug2, ...]}

3. 从每条Bug的 text (title + comments + parsed_root_cause) 提取关键词:
   - 中文分词: jieba 或简单 split
   - 过滤: 长度<2, 纯数字, 纯标点
   - 过滤垃圾词: hzhhnnas01, desaysv, uidq*, logs_*, DIDA*
   - 过滤日志目录名 regex: r'\d{8}[_-]\d{6}'
   - 过滤JIRA ID regex: r'CH\d+'

4. 统计 TF-IDF 或简单的词频:
   for kw in keywords_per_bug:
       freq[kw] = freq.get(kw, 0) + 1

5. 高频词写入 outputs/keywords_override.json:
   {"硬件-显示屏/解串器": ["dsi", "lvds", "黑屏", ...],
    "场景-CarPlay/Carlink": ["carplay", "回连", "hfp", ...],
    ...}

6. models.py 启动时自动加载:
   for cat, kws in keywords_override.items():
       for kw in kws:
           _rule_map[cat]["keywords"]["weak"].append(kw)
```

### 3.3 Step 3: 完整Bug清单附录

```bash
uv run python scripts/generate_bug_list_appendix.py
```

```
1. 读取 outputs/classification_data.json (673条)
2. 按 root_cause_category 分组
3. 按分类排序 (Bug数量降序)
4. 生成Markdown附录:
   
   ## 附录: 完整Bug分类清单
   
   ### 系统-PAG/动画库 (66条)
   | Bug ID | 标题 | 根因 | 修复状态 | 匹配关键词 |
   |--------|------|------|----------|-----------|
   | BUG20260416_09629 | ... | ... | ... | ... |
   ...
   
   ### 场景-CarPlay/Carlink (55条)
   ...

5. 拼接: report_refined.md + 附录 → report_refined_complete.md
6. 总行数约 1500-1600 行
```

### 3.4 Step 4: 趋势报告

```bash
uv run python scripts/trend_heatmap_report.py
```

```
1. 读取 analyzed_bugs.json → 历史快照 run_history (50轮)
2. 生成 HTML 趋势看板:
   - Chart.js 折线图: 每类Bug数量随时间变化
   - 热力图: Module × 时间
   - 修复率趋势: 已修复占比变化
3. 输出: outputs/trend_heatmap_report.html (约23KB)
```

### 3.5 Step 5: Obsidian同步

```bash
uv run python scripts/sync_to_obsidian.py
```

```
1. 读取 analyzed_bugs.json
2. 读取 FINE_GRAINED_RULES (28类)

3. A. 概览笔记: 黑卡闪问题提炼分析.md
   ---
   tags: [黑卡闪, 问题分析]
   created: 2026-05-27
   ---
   # 黑卡闪问题提炼分析
   - Bug总数: 673
   - 已修复: xxx (xx%)
   - [[分类趋势]] | [[修复状态]]

4. B. 25类分类笔记: 黑卡闪专项课题/分类分析/{分类名}.md
   每篇内容:
   ---
   tags: [黑卡闪, 分类分析, {分类名}]
   ---
   # {分类名}
   - Bug总数: N (修复率: xx%)
   - 趋势: ✅收敛 / 🔶收敛中 / 🔴需关注
   
   | Bug ID | 标题 | 根因 | 状态 |
   |--------|------|------|------|
   | ... | ... | ... | ... |

5. C. 趋势笔记:
   趋势/分类趋势.md: 25类变化趋势表
   趋势/修复状态.md: 已修复/未修复/无法复现统计

6. 总计28篇, 写入 Obsidian Vault
```

### 3.6 Step 6: 经验库关键词反哺

```bash
uv run python scripts/export_exp_keywords.py --min-confidence 0.7 --min-hits 2
```

```
1. GET http://10.219.9.92:8765/experiences/list
   → 所有经验记录

2. 过滤:
   confidence >= 0.7 AND hit_count >= 2

3. 按分类聚合关键词:
   for exp in filtered:
       keywords_by_cat[exp["category"]].extend(exp["keywords"])

4. 去重 + 排序 → 写入 outputs/keywords_override.json
5. models.py 下次启动自动加载
```

---

## 第四部分：数据文件详解

### 4.1 classification_data.json (673条)

```json
[
  {
    "bug_id": "BUG20260513_06373",
    "title": "【0513】【分屏】分屏界面偶发猎鹰辅助驾驶界面黑屏",
    "status": "Closed",
    "severity": "B",
    "module": "底软",
    "root_cause_category": "需人工判断",
    "fix_status": "已修复",
    "score": "0",
    "matched_keywords": "",
    "parsed_root_cause": "根本原因暂不确定...",
    "parsed_fix_method": "",
    "comments": ""
  }
]
```

### 4.2 analyzed_bugs.json

```json
{
  "_meta": {
    "last_run": "2026-05-27 17:30:00",
    "source_file": "Bug_20260521103307.xlsx",
    "total_analyzed": 673,
    "category_trend": {
      "系统-PAG/动画库": {"total": 66, "fixed": 45, "fix_rate": 68.2, "trend": "🔶 收敛中"},
      ...
    },
    "module_heatmap": {"底软": 120, "System UI": 89, ...},
    "run_history": [
      {"timestamp": "2026-05-21 10:00:00", "total": 665, "categories": {...}},
      {"timestamp": "2026-05-27 17:30:00", "total": 673, "categories": {...}},
      ... (保留50轮)
    ]
  },
  "bugs": {
    "BUG20260513_06373": {
      "category": "需人工判断",
      "fix_status": "已修复",
      "refined_at": "2026-05-27 17:30:00",
      "status": "Closed",
      "severity": "B",
      "module": "底软",
      "title": "【0513】【分屏】..."
    }
  }
}
```

### 4.3 golden_examples.json (53条金标准)

```json
{
  "硬件-显示屏/解串器": [
    {
      "bug_id": "BUG20260507_01362",
      "title": "屏线束不稳触发掉link导致仪表闪屏",
      "root_cause": "屏线束不稳触发 掉link",
      "keywords": "解串器, 掉link, 屏线束",
      "score": 9
    }
  ],
  "场景-CarPlay/Carlink": [...]
}
```

### 4.4 pending_categories.json

```json
{
  "系统-UI/弹窗": ["BUG20260506_00685", "BUG20260430_18468"],
  "应用-卡顿/响应": ["BUG20260519_10232"]
}
```

### 4.5 keywords_override.json

```json
{
  "系统-PAG/动画库": ["pag动画", "壁纸加载", "渲染超时", ...],
  "场景-CarPlay/Carlink": ["carplay", "回连", "hfp", ...]
}
```

---

## 第五部分：服务器API调用时序

```
本地引擎                                    服务器 10.219.9.92:8765
─────────────────────────────────────────────────────────────────

CrewAI启动:
  无API调用                                  
  (分类规则来自本地 models.py)

data_analyst:
  [工具调用] ExcelIssueTool
  [工具调用] BugKnowledgeTool
  → classification_data.json
  
issue_refiner:
  POST /match ──────────────────────→  match_experience()
    {project, bug_text, top_n=3}        SELECT experiences WHERE project=?
                                        → 关键词匹配打分
                                        → 返回 top3
  ←─────────────────────────────────  {count, results}
  
  [LLM推理精校]
  
  POST /experience ─────────────────→  upsert_experience()
    {project, category, root_cause,     同项目+分类+根因→更新hit_count
     solution, keywords, confidence}    新经验→INSERT
  ←─────────────────────────────────  {id, status:"ok"}

report_writer:
  POST /match ──────────────────────→  match_experience()
    (查经验去重)                        同上
  ←─────────────────────────────────

后处理 Step 1 (LLM精校):
  POST DeepSeek API ────────────────→  api.deepseek.com/v1/chat/completions
    (分批, 10条/批)                    model=deepseek-v4-flash
  ←─────────────────────────────────  Markdown表格

后处理 Step 6 (经验库反哺):
  GET /experiences/list ─────────────→  SELECT * FROM experiences
  ←─────────────────────────────────  [所有经验]
  
  (本地处理: 过滤confidence>=0.7 → 写入keywords_override.json)
```

---

## 第六部分：完整调用图

```
refine_complete()
│
├── _filtered_inputs()
│   ├── _find_latest_excel()             → 找到最新 Bug_*.xlsx
│   ├── _count_excel_rows()              → 统计行数
│   ├── _is_forced()                     → 检查 FORCE_FULL_RUN
│   └── _incremental_filter()
│       ├── load_workbook()              → 打开Excel
│       ├── BugKnowledgeTool.filter_new_and_changed()
│       │   ├── _load_static()           → 读 analyzed_bugs.json
│       │   └── 对比 bug_id + status
│       └── _save_static()               → 更新 source_file
│
├── MyCrew().refinement_crew().kickoff()
│   │
│   ├── [Agent 1] data_analyst
│   │   ├── ExcelIssueTool._run()
│   │   │   ├── load_workbook()          → 打开Excel
│   │   │   ├── _get_worksheet()         → 大小写不敏感匹配sheet
│   │   │   ├── _map_columns()           → 列名映射 (aliases)
│   │   │   ├── for each record:
│   │   │   │   ├── _build_analysis_text() → Title+Comments+Cause+Solved
│   │   │   │   ├── _classify_weighted()   → 28类加权匹配
│   │   │   │   ├── _parse_comments()      → 提取根因/修复
│   │   │   │   └── _classify_fix_status() → 判断修复状态
│   │   │   ├── _persist_to_kb()         → 写 analyzed_bugs.json
│   │   │   │   └── 计算 category_trend, module_heatmap
│   │   │   │   └── 追加 run_history 快照
│   │   │   ├── _write_classification_json() → classification_data.json
│   │   │   └── 组装Markdown输出
│   │   └── BugKnowledgeTool._run(action="filter")
│   │       └── json.dumps(kb)
│   │
│   ├── [Agent 2] issue_refiner
│   │   ├── ExperienceMatchTool._run()
│   │   │   └── POST http://10.219.9.92:8765/match
│   │   │       → experience_db.match_experience()
│   │   │       → 关键词匹配打分 → 返回top3
│   │   ├── [LLM 精校推理]
│   │   └── ExperienceUpdateTool._run()
│   │       └── POST http://10.219.9.92:8765/experience
│   │           → experience_db.upsert_experience()
│   │
│   └── [Agent 3] report_writer
│       ├── ExperienceMatchTool._run()
│       │   └── POST /match (经验去重)
│       └── [LLM 生成报告]
│           → outputs/report_refined.md
│
├── Step 1: LLM批量精校
│   └── subprocess: uv run python scripts/llm_reclassify_manual.py --batch 10
│       ├── load_data(JSON_PATH)          → 读 classification_data.json
│       ├── 筛选 "需人工判断"
│       ├── for each batch (10条):
│       │   ├── call_deepseek()           → POST DeepSeek API
│       │   │   └── system=SYS_PROMPT (含Few-shot)
│       │   └── parse_response()          → 解析Markdown表格
│       ├── 收集 new_category → pending_categories.json
│       └── update_classification_json()  → 写回
│
├── Step 2: 关键词自学习
│   └── subprocess: uv run python scripts/learn_keywords_from_llm.py
│       └── 分词 → 过滤 → TF-IDF → keywords_override.json
│
├── Step 3: 附录拼接
│   └── subprocess: uv run python scripts/generate_bug_list_appendix.py
│       └── 读JSON → 按类分组 → 生成Markdown → 拼接
│
├── Step 4: 趋势报告
│   └── subprocess: uv run python scripts/trend_heatmap_report.py
│       └── 读历史快照 → Chart.js → HTML
│
├── Step 5: Obsidian同步
│   └── subprocess: uv run python scripts/sync_to_obsidian.py
│       └── 28篇笔记 → Obsidian Vault
│
└── Step 6: 经验库反哺
    └── subprocess: uv run python scripts/export_exp_keywords.py
        └── GET /experiences/list → 过滤 → keywords_override.json
```

---

*最后更新: 2026-05-27 | 作者: uidq1474*
