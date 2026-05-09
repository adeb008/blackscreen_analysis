from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from openpyxl import load_workbook
from pydantic import BaseModel, Field


class ExcelIssueToolInput(BaseModel):
    excel_path: str = Field(..., description="Excel file path, for example D:/my_crew/data/black_flash_issues.xlsx")
    sheet_name: str | None = Field(None, description="Worksheet name. If empty, the first sheet is used.")
    max_examples: int = Field(20, description="Maximum number of typical issue examples to include.")


# ============================================================
# 根因分类规则：匹配 Bug 描述/根因文本 → 归类到 11 个根因大类
# ============================================================
ROOT_CAUSE_RULES: list[dict] = [
    {
        "name": "SAIL/safetymonitor 异常类",
        "keywords": ["safetymonitor", "SAIL", "75ms", "MD response", "APSS", "ramdump", "VSENS", "safety_mx"],
        "case_tags": ["Case 2", "Case 6", "Case 7"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "IDPS / QNX Kernel Crash 类",
        "keywords": ["idps", "nidps", "kernel crash", "kernel shutdown"],
        "case_tags": ["Case 2", "Case 7"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "心跳/握手/通信异常类",
        "keywords": ["SPI", "心跳", "0x80", "0x5501", "握手", "heartbeat", "保活"],
        "case_tags": ["Case 5", "Case 6"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "内存问题类",
        "keywords": ["内存", "memory", "踩踏", "踩内存", "leak", "kasan", "CPU负载"],
        "case_tags": ["Case 2"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "Android 应用层问题",
        "keywords": ["Activity", "lifecycle", "watchdog", "ANR", "surfaceflinger", "SMMU fault", "adreno"],
        "case_tags": ["Case 1"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "电源/供电问题",
        "keywords": ["电源", "供电", "电流", "逆变器", "电压"],
        "case_tags": ["Case 2"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "软件配置/升级问题",
        "keywords": ["升级", "回滚", "共板", "配置", "标定文件"],
        "case_tags": ["Case 4", "Case 5"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "NOC Error/DDR/900E(硬件)",
        "keywords": ["NOC error", "DDR", "900E", "0xac12e0", "NOR error", "backtrace"],
        "case_tags": ["Case 7"],
        "section": "二、未修复/挂起的问题",
    },
    {
        "name": "io-sock/emac 驱动",
        "keywords": ["io-sock", "emac", "驱动挂死"],
        "case_tags": ["Case 5"],
        "section": "二、未修复/挂起的问题",
    },
    {
        "name": "测试手法/环境问题",
        "keywords": ["台架", "高温", "水冷", "串口板", "环境", "5A", "10A"],
        "case_tags": ["Case 1", "Case 2"],
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "无法复现/日志不全",
        "keywords": ["无法复现", "日志不全", "日志缺失", "缺少log"],
        "case_tags": [],
        "section": "三、核心问题分类统计",
    },
]

# ============================================================
# 状态判断关键词
# ============================================================
FIXED_STATUS_WORDS = ["closed", "done", "fixed", "verified", "已关闭", "已修复", "已验证", "关闭"]
PENDING_STATUS_WORDS = ["postpone", "open", "new", "挂起", "待处理", "待分析", "依赖"]
UNREPRODUCIBLE_WORDS = ["无法复现", "未复现", "can't reproduce", "cannot reproduce", "日志不全"]


class ExcelIssueTool(BaseTool):
    name: str = "Excel Black-Screen/Freeze/Flicker Issue Analyzer"
    description: str = (
        "Read an issue-list Excel file and return a structured markdown summary "
        "including field mapping, distributions, root cause classification (11 categories), "
        "fixed/pending grouping, cross tables, keyword analysis, and typical examples."
    )
    args_schema: type[BaseModel] = ExcelIssueToolInput

    column_aliases: dict[str, list[str]] = {
        "bug_id": ["bug id", "bugid", "id", "缺陷id", "问题id"],
        "title": ["title", "标题", "问题标题", "summary", "问题现象"],
        "comments": ["comments", "comment", "备注", "评论", "说明", "分析说明"],
        "root_cause": ["root cause", "根因", "根因分析", "原因", "rootcause", "cause analysis", "cause_analysis", "Cause Analysis"],
        "fix_method": ["fix", "fix method", "修复方式", "修复方案", "修复"],
        "status": ["status", "状态", "问题状态", "处理状态", "关闭状态"],
        "severity": ["severity", "严重度", "等级", "优先级", "风险等级"],
        "assignee": ["assignee", "责任人", "负责人", "处理人", "owner"],
        "creator": ["creator", "创建人", "提出人", "提交人", "reporter"],
        "module": ["module", "模块", "系统", "功能", "域", "component"],
        "frequency": ["frequency", "频次", "复现频率", "发生频率", "概率"],
        "analyzer": ["analyzer", "分析人", "分析责任人"],
        "sample_stage": ["sample stage", "样件阶段", "阶段", "sample", "stage"],
    }

    def _run(self, excel_path: str, sheet_name: str | None = None, max_examples: int = 20) -> str:
        path = Path(excel_path)
        if not path.exists():
            return f"Error: Excel file not found: {excel_path}"

        workbook = load_workbook(path, read_only=True, data_only=True)
        worksheet = workbook[sheet_name] if sheet_name else workbook[workbook.sheetnames[0]]
        rows = list(worksheet.iter_rows(values_only=True))
        if not rows:
            return "Error: Excel sheet is empty."

        headers = [self._clean_cell(value) or f"Unnamed Column {index + 1}" for index, value in enumerate(rows[0])]
        records = self._records_from_rows(headers, rows[1:])
        if not records:
            return "Error: Excel sheet has headers but no valid data rows."

        mapping = self._map_columns(headers, records)

        # ---- 对每条记录做根因分类 ----
        for record in records:
            text = self._build_analysis_text(record, mapping)
            rc = self._classify_root_cause(text)
            record["_root_cause_category"] = rc["category"]
            record["_root_cause_section"] = rc["section"]
            record["_root_cause_case_tags"] = ", ".join(rc["case_tags"])
            record["_root_cause_keywords"] = ", ".join(rc["matched_keywords"])

            # 从 Comments 解析根因和修复方式（优先使用独立列 > Comments 解析）
            dedicated_rc = self._value(record, mapping.get("root_cause"))
            parsed = self._parse_comments(self._value(record, mapping.get("comments")))
            record["_parsed_root_cause"] = dedicated_rc or parsed["root_cause"]
            record["_parsed_fix_method"] = parsed["fix_method"]

            # 判断是否已修复
            status_val = self._value(record, mapping.get("status")).lower()
            text_lower = text.lower()
            if any(w in text_lower for w in UNREPRODUCIBLE_WORDS):
                record["_fix_status"] = "无法复现"
            elif any(w in status_val for w in PENDING_STATUS_WORDS):
                record["_fix_status"] = "未修复/挂起"
            elif any(w in status_val for w in FIXED_STATUS_WORDS):
                record["_fix_status"] = "已修复"
            else:
                # 根据 section 推断
                if rc["section"] == "二、未修复/挂起的问题":
                    record["_fix_status"] = "未修复/挂起"
                else:
                    record["_fix_status"] = "已修复"

        # ---- 组装输出 ----
        lines: list[str] = []
        lines.append("# 黑卡闪问题 Excel 结构化分析摘要")
        lines.append(f"- 文件: {excel_path}")
        lines.append(f"- Sheet: {worksheet.title}")
        lines.append(f"- 数据行数: {len(records)}")
        lines.append(f"- 根因分类数: 11 类")

        # ---- 字段映射 ----
        lines.append("\n## 字段映射")
        for std_name in ["bug_id", "title", "comments", "root_cause", "fix_method", "status",
                         "severity", "assignee", "creator", "module", "frequency", "analyzer", "sample_stage"]:
            match = mapping.get(std_name)
            lines.append(f"- {std_name}: {match or '未识别'}")

        # ---- 字段缺失 ----
        lines.append("\n## 字段缺失情况")
        for column, count in self._missing_counts(headers, records).most_common(10):
            ratio = count / len(records) * 100
            lines.append(f"- {column}: {count} ({ratio:.1f}%)")

        # ---- 标准分布 ----
        self._append_distribution(lines, "Status 分布", records, mapping.get("status"))
        self._append_distribution(lines, "Severity 分布", records, mapping.get("severity"))
        self._append_distribution(lines, "Module 分布", records, mapping.get("module"))
        self._append_distribution(lines, "Frequency 分布", records, mapping.get("frequency"))

        # ---- 根因分类统计 ----
        lines.append("\n## 根因分类统计")
        rc_counter: Counter = Counter()
        rc_section_map: dict[str, set[str]] = defaultdict(set)
        for record in records:
            cat = record.get("_root_cause_category", "未知")
            rc_counter[cat] += 1
            section = record.get("_root_cause_section", "未知")
            rc_section_map[cat].add(section)

        for cat, count in rc_counter.most_common():
            sections = ", ".join(rc_section_map[cat])
            ratio = count / len(records) * 100
            lines.append(f"- {cat}: {count} ({ratio:.1f}%) [{sections}]")

        # ---- 已修复 vs 未修复 vs 无法复现 ----
        lines.append("\n## 修复状态分组")
        fix_counter = Counter(r.get("_fix_status", "未知") for r in records)
        for status, count in fix_counter.most_common():
            ratio = count / len(records) * 100
            lines.append(f"- {status}: {count} ({ratio:.1f}%)")

        # ---- 各根因大类下的典型 Bug 列表 ----
        lines.append("\n## 各根因大类 Bug 清单")
        bugs_by_cat: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            bugs_by_cat[record.get("_root_cause_category", "未知")].append(record)

        for cat in sorted(bugs_by_cat, key=lambda c: len(bugs_by_cat[c]), reverse=True):
            bug_list = bugs_by_cat[cat]
            lines.append(f"\n### {cat}（{len(bug_list)} 条）")
            for bug in bug_list[:10]:  # 最多 10 条
                bug_id = self._value(bug, mapping.get("bug_id")) or "无 ID"
                title = self._value(bug, mapping.get("title")) or "无标题"
                rc = bug.get("_parsed_root_cause") or self._value(bug, mapping.get("root_cause")) or "无根因"
                fix = bug.get("_parsed_fix_method") or self._value(bug, mapping.get("fix_method")) or "无修复方式"
                status = self._value(bug, mapping.get("status")) or "无状态"
                lines.append(f"  - [{bug_id}] {title}")
                lines.append(f"    - 根因: {rc[:200]}")
                lines.append(f"    - 修复: {fix[:200]}")
                lines.append(f"    - 状态: {status} | Case 标签: {bug.get('_root_cause_case_tags', '')}")

        # ---- 交叉统计 ----
        self._append_cross_table(lines, "Module x Severity", records, mapping.get("module"), mapping.get("severity"))
        self._append_cross_table(lines, "Module x 根因分类", records, mapping.get("module"), "_root_cause_category")
        self._append_cross_table(lines, "根因分类 x 修复状态", records, "_root_cause_category", "_fix_status")

        # ---- 典型样例 ----
        lines.append(f"\n## 典型问题样例（前 {max_examples} 条）")
        for index, record in enumerate(records[:max_examples], 1):
            bug_id = self._value(record, mapping.get("bug_id")) or "无 Bug ID"
            title = self._value(record, mapping.get("title")) or "无 Title"
            severity = self._value(record, mapping.get("severity")) or "无 Severity"
            status = self._value(record, mapping.get("status")) or "无 Status"
            rc_cat = record.get("_root_cause_category", "未知")
            fix_st = record.get("_fix_status", "未知")
            comments = self._value(record, mapping.get("comments"))
            root_cause = record.get("_parsed_root_cause") or self._value(record, mapping.get("root_cause"))
            fix_method = record.get("_parsed_fix_method") or self._value(record, mapping.get("fix_method"))
            lines.append(
                f"{index}. [{bug_id}] {title} | "
                f"根因分类={rc_cat} | 修复状态={fix_st} | Severity={severity} | Status={status}"
            )
            if root_cause:
                lines.append(f"   - 根因: {root_cause[:200]}")
            if fix_method:
                lines.append(f"   - 修复: {fix_method[:200]}")
            elif comments:
                lines.append(f"   - 备注: {comments[:200]}")

        # ---- 给后续 Agent 的分析提示 ----
        lines.append("\n## 后续 Agent 分析提示")
        lines.append("- 根因分类: 每条 Bug 已按 11 类根因规则自动分类，field `_root_cause_category`")
        lines.append("- 修复状态: 已分入 已修复 / 未修复/挂起 / 无法复现，field `_fix_status`")
        lines.append("- 关联 Case: 已标注每个 Bug 关联的 Case 标签，field `_root_cause_case_tags`")
        lines.append("- 报告结构建议: 按「已修复→未修复→统计→经验→总结」五段式组织")

        return "\n".join(lines)

    # ---------- Comments 解析 ----------

    def _parse_comments(self, comments: str) -> dict:
        """从 Comments 自由文本中解析出根因和修复方式。

        支持的格式（按优先级）:
          1. [root_cause]:xxx / [solution]:xxx    — 方括号标签格式
          2. 根本原因:xxx / 解决对策:xxx           — 中文标签格式
          3. 问题分析:xxx / 原因:xxx               — 分析标签格式
          4. 最后一条有意义的内容（兜底）           — 自由文本推断
          5. [Patch]:URL 提取为修复引用
        """
        if not comments:
            return {"root_cause": "", "fix_method": ""}

        root_cause = ""
        fix_method = ""
        import re

        # [root_cause]:xxx
        m = re.search(r'\[root_cause\][：:]\s*(.+?)(?=\n\d+#|\Z)', comments, re.DOTALL)
        if not m:
            m = re.search(r'\[root_cause\]\s*=\s*(.+?)(?=\n\d+#|\Z)', comments, re.DOTALL)
        if m:
            root_cause = m.group(1).strip()

        # [solution]:xxx
        m = re.search(r'\[solution\][：:]\s*(.+?)(?=\n\d+#|\Z)', comments, re.DOTALL)
        if m:
            fix_method = m.group(1).strip()

        # [Patch]:URL (当 solution 未命中时)
        if not fix_method:
            m = re.search(r'\[Patch\]:\s*(\S+)', comments)
            if m:
                fix_method = f"Patch: {m.group(1).strip()}"

        # 中文标签（仅当方括号未命中时）
        if not root_cause:
            for label in ("根本原因", "根因分析", "根因", "原因分析"):
                m = re.search(rf'{label}[：:]\s*(.+?)(?=\n\d+#|\n\d\'#|\Z)', comments, re.DOTALL)
                if m:
                    root_cause = m.group(1).strip()
                    break

        if not fix_method:
            for label in ("解决对策", "修复方式", "修复方案", "对策"):
                m = re.search(rf'{label}[：:]\s*(.+?)(?=\n\d+#|\n\d\'#|\Z)', comments, re.DOTALL)
                if m:
                    fix_method = m.group(1).strip()
                    break

        # 问题分析/原因（更低优先级）
        if not root_cause:
            for label in ("问题分析", "原因"):
                m = re.search(rf'{label}[：:]\s*(.+?)(?=\n\d+#|\n\d\'#|\Z)', comments, re.DOTALL)
                if m:
                    root_cause = m.group(1).strip()
                    break

        # 兜底：取最后一条 comment 的正文
        if not root_cause and not fix_method:
            parts = re.split(r'\n\d+[#\']', comments)
            if parts:
                last = parts[-1].strip()
                last = re.sub(r'.*?创建时间：.*?\|.*', '', last)
                last = re.sub(r'.*?修改时间：.*?', '', last)
                last = re.sub(r'@\w+\(\w+\)', '', last)
                lines = [l.strip() for l in last.split('\n') if l.strip() and len(l.strip()) > 10]
                if lines:
                    root_cause = lines[-1][:200]

        return {"root_cause": root_cause.strip(), "fix_method": fix_method.strip()}

    # ---------- 根因分类 ----------

    def _build_analysis_text(self, record: dict[str, str], mapping: dict[str, str | None]) -> str:
        parts = []
        for key in ("title", "comments", "root_cause"):
            col = mapping.get(key)
            if col and record.get(col):
                parts.append(record[col])
        return "\n".join(parts)

    def _classify_root_cause(self, text: str) -> dict:
        text_lower = text.lower()
        best = {"category": "无法复现/日志不全", "section": "三、核心问题分类统计", "case_tags": [], "matched_keywords": []}
        best_score = 0
        for rule in ROOT_CAUSE_RULES:
            score = 0
            hits = []
            for kw in rule["keywords"]:
                if kw.lower() in text_lower:
                    score += 1
                    hits.append(kw)
            if score > best_score:
                best_score = score
                best = {
                    "category": rule["name"],
                    "section": rule["section"],
                    "case_tags": rule["case_tags"],
                    "matched_keywords": hits,
                }
        return best

    # ---------- 数据处理 ----------

    def _records_from_rows(self, headers: list[str], rows: list[tuple[Any, ...]]) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for row in rows:
            record = {}
            for index, header in enumerate(headers):
                record[header] = self._clean_cell(row[index] if index < len(row) else None)
            if any(record.values()):
                records.append(record)
        return records

    def _map_columns(self, headers: list[str], records: list[dict[str, str]]) -> dict[str, str | None]:
        mapping = {key: self._guess_column_by_name(headers, aliases) for key, aliases in self.column_aliases.items()}
        if mapping.get("title") is None:
            mapping["title"] = self._guess_long_text_column(headers, records)
        if mapping.get("comments") is None:
            mapping["comments"] = self._guess_long_text_column(headers, records, exclude={mapping.get("title")})
        if mapping.get("status") is None:
            mapping["status"] = self._guess_status_column(headers, records)
        if mapping.get("severity") is None:
            mapping["severity"] = self._guess_severity_column(headers, records)
        return mapping

    def _guess_column_by_name(self, headers: list[str], aliases: list[str]) -> str | None:
        normalized_headers = [(header, self._normalize(header)) for header in headers]
        normalized_aliases = [self._normalize(alias) for alias in aliases]
        for header, normalized_header in normalized_headers:
            for alias in normalized_aliases:
                if alias and (alias == normalized_header or alias in normalized_header or normalized_header in alias):
                    return header
        return None

    def _guess_long_text_column(self, headers: list[str], records: list[dict[str, str]],
                                exclude: set[str | None] | None = None) -> str | None:
        exclude = exclude or set()
        best_column = None
        best_score = 0.0
        for header in headers:
            if header in exclude:
                continue
            values = [record.get(header, "") for record in records if record.get(header)]
            if not values:
                continue
            avg_len = sum(len(value) for value in values) / len(values)
            unique_ratio = len(set(values)) / len(values)
            score = avg_len * 0.7 + unique_ratio * 20
            if score > best_score:
                best_score = score
                best_column = header
        return best_column if best_score >= 15 else None

    def _guess_status_column(self, headers: list[str], records: list[dict[str, str]]) -> str | None:
        words = ["open", "closed", "done", "fixed", "reject", "new", "active", "处理中", "已关闭", "关闭", "待处理", "已解决"]
        return self._guess_by_content_words(headers, records, words, threshold=0.25)

    def _guess_severity_column(self, headers: list[str], records: list[dict[str, str]]) -> str | None:
        words = ["critical", "major", "minor", "blocker", "high", "medium", "low", "严重", "一般", "高", "中", "低", "s", "p"]
        return self._guess_by_content_words(headers, records, words, threshold=0.2)

    def _guess_by_content_words(self, headers: list[str], records: list[dict[str, str]],
                                words: list[str], threshold: float) -> str | None:
        for header in headers:
            values = [record.get(header, "").lower() for record in records if record.get(header)]
            if not values:
                continue
            hit_count = sum(any(word in value for word in words) for value in values)
            if hit_count / len(values) >= threshold:
                return header
        return None

    def _missing_counts(self, headers: list[str], records: list[dict[str, str]]) -> Counter:
        return Counter({header: sum(1 for record in records if not record.get(header)) for header in headers})

    def _append_distribution(self, lines: list[str], title: str, records: list[dict[str, str]], column: str | None) -> None:
        if not column:
            lines.append(f"\n## {title}\n- 未识别对应字段")
            return
        lines.append(f"\n## {title}")
        for value, count in self._counts(records, column).most_common(15):
            ratio = count / len(records) * 100
            lines.append(f"- {value}: {count} ({ratio:.1f}%)")

    def _append_cross_table(self, lines: list[str], title: str, records: list[dict[str, str]],
                            row_column: str | None, value_column: str | None) -> None:
        if not row_column or not value_column:
            lines.append(f"\n## {title}\n- 未识别足够字段")
            return
        lines.append(f"\n## {title}")
        grouped: dict[str, Counter] = defaultdict(Counter)
        for record in records:
            row_value = record.get(row_column) or "空值"
            value = record.get(value_column) or "空值"
            grouped[row_value][value] += 1
        for row_value, counter in sorted(grouped.items(), key=lambda item: sum(item[1].values()), reverse=True)[:12]:
            parts = [f"{v}: {c}" for v, c in counter.most_common(8)]
            lines.append(f"- {row_value}: " + "; ".join(parts))

    def _counts(self, records: list[dict[str, str]], column: str) -> Counter:
        return Counter(record.get(column) or "空值" for record in records)

    def _value(self, record: dict[str, str], column: str | None) -> str:
        return record.get(column, "") if column else ""

    def _clean_cell(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _normalize(self, value: str) -> str:
        return "".join(str(value).lower().replace("_", " ").replace("-", " ").split())
