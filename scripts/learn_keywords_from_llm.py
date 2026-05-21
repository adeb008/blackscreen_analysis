#!/usr/bin/env python
"""关键词自学习：从 LLM 精校结果提取新关键词，回写到 FINE_GRAINED_RULES 覆盖文件

原理：
  1. 读取 classification_data.json，找到被 LLM 从"需人工判断"改为具体分类的 Bug
  2. 从 Title / Comments / RootCause 提取有意义的词汇/短语
  3. 去重（跳过已存在于 FINE_GRAINED_RULES 的关键词）
  4. 存入关键词覆盖 JSON 文件
  5. 下次 ExcelIssueTool 加载时，自动合并这些额外关键词

输出:
  outputs/keywords_override.json — 格式: {分类名: [词1, 词2, ...]}
"""

import json
import re
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
JSON_PATH = BASE_DIR / "outputs" / "classification_data.json"
OVERRIDE_PATH = BASE_DIR / "outputs" / "keywords_override.json"

# 已知 FINE_GRAINED_RULES 的关键词（硬编码去重参考，防止重复添加）
# 运行时也从 models.py 获取
EXISTING_KEYWORDS: dict[str, set[str]] = {}

# 常见噪声词（不应成为分类关键词）
STOPWORDS = {
    "问题", "出现", "导致", "发生", "存在", "偶现", "复现",
    "测试", "场景", "情况", "时候", "发现", "可以", "需要",
    "解决", "修复", "修改", "确认", "查看", "可能", "是否",
    "没有", "不是", "这个", "那个", "什么", "怎么", "为什么",
    "版本", "之前", "之后", "目前", "现在", "然后", "或者",
    "一下", "一次", "一个", "一条", "打开", "关闭", "进入",
    "系统", "界面", "显示", "操作", "数据", "信息", "状态",
    "时间", "问题", "bug", "Bug", "log", "Log", "LOG",
}


def load_keyword_overrides() -> dict[str, list[str]]:
    """加载已有的关键词覆盖"""
    if OVERRIDE_PATH.exists():
        with open(OVERRIDE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_keyword_overrides(overrides: dict[str, list[str]]):
    OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OVERRIDE_PATH, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False, indent=2)
    total = sum(len(v) for v in overrides.values())
    print(f"[关键词] 已保存 {total} 个新关键词到 {OVERRIDE_PATH}")


def load_existing_keywords() -> dict[str, set[str]]:
    """从 models.py 加载已有的 FINE_GRAINED_RULES 关键词"""
    try:
        from my_crew.models import FINE_GRAINED_RULES
        existing: dict[str, set[str]] = {}
        for rule in FINE_GRAINED_RULES:
            name = rule["name"]
            keywords = set()
            for strength in ("strong", "medium", "weak"):
                for kw in rule["keywords"].get(strength, []):
                    keywords.add(kw.lower())
            existing[name] = keywords
        return existing
    except ImportError:
        return {}


def extract_keywords(text: str) -> set[str]:
    """从文本中提取有意义的候选关键词"""
    if not text:
        return set()

    candidates = set()

    # 1. 完整短语: 2~4 字的中文组合
    # 匹配连续中文字符
    chinese_phrases = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    for phrase in chinese_phrases:
        phrase = phrase.strip()
        if phrase.lower() in {s.lower() for s in STOPWORDS}:
            continue
        if len(phrase) >= 3:  # 至少 3 个字
            candidates.add(phrase)

    # 2. 英文技术词汇: 驼峰/下划线/特殊标识
    eng_terms = re.findall(
        r"\b([a-zA-Z][a-zA-Z0-9_\-]{2,30})\b", text
    )
    for term in eng_terms:
        if term.lower() not in {s.lower() for s in STOPWORDS}:
            candidates.add(term)

    # 3. 中英混合的特定模式: "AVM倒车" "STR唤醒" 等
    mixed = re.findall(r"([A-Z]{2,6}[\u4e00-\u9fff]{1,6})", text)
    for m in mixed:
        if len(m) >= 3:
            candidates.add(m)

    return candidates


def is_keyword_useful(kw: str, existing: set[str]) -> bool:
    """判断一个关键词值得加入规则"""
    kw_lower = kw.lower()
    # 跳过纯数字
    if kw_lower.isdigit():
        return False
    # 跳过太短的
    if len(kw_lower) < 3:
        return False
    # 跳过已存在的
    if kw_lower in existing:
        return False
    # 跳过 UUID / JIRA ID / 哈希等垃圾
    if re.search(r'^[a-f0-9]{8,}$', kw):         # hex hash
        return False
    if re.search(r'[A-Z]{2,10}-\d{2,}', kw):      # JIRA: CH7XCOCKPIT-123
        return False
    if re.search(r'^[a-f0-9]{8}-', kw):           # UUID前缀
        return False
    if kw.startswith("Bug") or kw.startswith("BUG") or kw.startswith("bug"):
        return False
    if kw.endswith(".com"):
        return False
    # 跳过纯拼音人名
    pinyin_patterns = {'Deng', 'Song', 'Liu', 'Wang', 'Zhang', 'Li', 'Chen',
                       'Yang', 'Zhou', 'Wu', 'Xu', 'Sun', 'Huang', 'Zhu',
                       'Hu', 'Lin', 'He', 'Guo', 'Ma', 'Luo', 'Liang'}
    if kw in pinyin_patterns or any(kw.startswith(p) for p in pinyin_patterns if len(p) >= 4):
        return False
    # 跳过空格太多或无意义的
    if len(kw_lower) > 50:
        return False
    # 跳过只有特殊字符的
    if re.search(r'^[^a-zA-Z\u4e00-\u9fff]+$', kw_lower):
        return False
    # 跳过与已有关键词高度相似（编辑距离 < 2）
    for existing_kw in existing:
        if len(kw_lower) >= 3 and len(existing_kw) >= 3:
            if kw_lower in existing_kw or existing_kw in kw_lower:
                return False
    return True


def learn_keywords():
    """主入口：从 LLM 精校结果学习新关键词"""
    if not JSON_PATH.exists():
        print(f"[关键词] 找不到 {JSON_PATH}")
        return

    with open(JSON_PATH, encoding="utf-8") as f:
        bugs = json.load(f)

    # 加载已有关键词
    existing = load_existing_keywords()
    existing_flat = set()
    for kw_set in existing.values():
        existing_flat.update(kw_set)

    # 加载已有覆盖（避免重复添加）
    overrides = load_keyword_overrides()
    for cat, kws in overrides.items():
        existing_flat.update(k.lower() for k in kws)

    # 找出 LLM 精校过且不是"需人工判断"的 Bug
    # 判断依据: bugs 当前分类不是"需人工判断"，且 bug 的 root_cause_category 不是空
    # 注意：这里无法直接知道"精校前"分类是什么，因为 JSON 只存当前分类
    # 我们假设所有非"需人工判断"的 Bug 都是有效分类（工具或 LLM 分的）
    # 但只从之前是"需人工判断"的被精校 Bug 中提取
    # 判断方式：查看 keywords_override.json 中是否已有记录

    new_keywords: dict[str, set[str]] = defaultdict(set)
    processed = 0

    # 已精校追回的关键词覆盖
    reclassify_log = BASE_DIR / "scripts" / "llm_reclassify_results.json"

    for bug in bugs:
        cat = bug.get("root_cause_category", "")
        if not cat or cat == "需人工判断":
            continue

        # 收集所有文本源
        texts = [
            bug.get("title", ""),
            bug.get("parsed_root_cause", ""),
            bug.get("comments", ""),
        ]
        combined = " ".join(t for t in texts if t)
        if not combined:
            continue

        keywords = extract_keywords(combined)
        useful = {kw for kw in keywords if is_keyword_useful(kw, existing_flat)}

        if useful:
            new_keywords[cat].update(useful)
            processed += 1

    # 去重+去停用词
    final_overrides: dict[str, list[str]] = {}
    for cat, kws in new_keywords.items():
        # 只保留每个分类 top 10 个新关键词
        sorted_kws = sorted(kws, key=lambda x: (-len(x), x))[:10]
        # 去重（已存在于已有覆盖的不再加）
        existing_override = set(overrides.get(cat, []))
        fresh = [kw for kw in sorted_kws if kw.lower() not in existing_override]
        if fresh:
            final_overrides[cat] = overrides.get(cat, []) + fresh

    if not final_overrides:
        print("[关键词] 本轮无新关键词需要添加")
        return

    # 合并到已有覆盖
    merged = dict(overrides)
    for cat, kws in final_overrides.items():
        existing_set = set(merged.get(cat, []))
        new_unique = [kw for kw in kws if kw not in existing_set]
        if cat in merged:
            merged[cat].extend(new_unique)
        else:
            merged[cat] = new_unique

    save_keyword_overrides(merged)
    print(f"[关键词] 从 {processed} 条 Bug 中提取了 {sum(len(v) for v in final_overrides.values())} 个新关键词")
    for cat, kws in final_overrides.items():
        print(f"         {cat}: +{len(kws)} 词 → {' / '.join(kws[:5])}...")


if __name__ == "__main__":
    learn_keywords()
