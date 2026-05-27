"""
批量从 classification_data.json 写入经验库
策略：按 root_cause_category 分组，每组聚合关键词/bug_id，写一条代表经验
"""
import json, os, requests
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv(r"D:\my_crew\.env")
API_BASE = os.environ.get("EXPERIENCE_API_URL", "http://10.219.9.92:8765")
API_KEY  = os.environ.get("EXPERIENCE_API_KEY", "")
SCHEMA   = os.environ.get("PROJECT_SCHEMA", "8775_T1Q_国内")
HEADERS  = {"X-API-Key": API_KEY, "Content-Type": "application/json"}

data = json.load(open(r"D:\my_crew\outputs\classification_data.json", encoding="utf-8"))
print(f"总条数: {len(data)}")

# 按分类聚合
groups = defaultdict(list)
for item in data:
    cat = item.get("root_cause_category", "未分类")
    groups[cat].append(item)

print(f"分类数: {len(groups)}")

ok_count = 0
fail_count = 0

for cat_full, items in groups.items():
    # 拆分 category / subcategory
    if "-" in cat_full:
        category, subcategory = cat_full.split("-", 1)
    else:
        category, subcategory = cat_full, ""

    # 聚合关键词（去重）
    kw_set = set()
    bug_ids = []
    root_causes = []
    solutions = []
    for item in items:
        for kw in (item.get("matched_keywords") or "").split(","):
            kw = kw.strip()
            if kw:
                kw_set.add(kw)
        if item.get("bug_id"):
            bug_ids.append(item["bug_id"])
        if item.get("parsed_root_cause"):
            root_causes.append(item["parsed_root_cause"])
        if item.get("parsed_fix_method"):
            solutions.append(item["parsed_fix_method"])

    # 取最有代表性的根因/解决方案（优先非空）
    root_cause = next((r for r in root_causes if len(r) > 5), category)
    solution   = next((s for s in solutions if len(s) > 5), "待补充")
    keywords   = list(kw_set)[:20] if kw_set else [category]
    source_bug = bug_ids[0] if bug_ids else ""
    # 置信度：条数越多越高
    confidence = min(0.5 + len(items) * 0.02, 0.95)
    summary    = f"{category}({subcategory})：{len(items)}条，主因：{root_cause[:60]}"

    payload = {
        "project": SCHEMA,
        "category": category,
        "subcategory": subcategory,
        "summary": summary,
        "root_cause": root_cause[:500],
        "solution": solution[:500],
        "keywords": keywords,
        "source_bug": source_bug,
        "confidence": round(confidence, 2),
    }

    try:
        resp = requests.post(f"{API_BASE}/experience", json=payload, headers=HEADERS, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            print(f"  OK id={d['id']}  [{category}] ({len(items)}条)")
            ok_count += 1
        else:
            print(f"  FAIL {resp.status_code} [{category}]: {resp.text[:100]}")
            fail_count += 1
    except Exception as e:
        print(f"  ERR [{category}]: {e}")
        fail_count += 1

print(f"\n写入完成: 成功={ok_count}  失败={fail_count}")

# 验证
resp = requests.get(f"{API_BASE}/experience", params={"schema": SCHEMA}, headers=HEADERS, timeout=5)
print(f"经验库当前总数: {resp.json().get('count', '?')}")
