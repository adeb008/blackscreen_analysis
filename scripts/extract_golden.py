
import json
from collections import defaultdict
from pathlib import Path
from my_crew.models import FINE_GRAINED_RULES

bugs = json.loads(Path('outputs/classification_data.json').read_text(encoding='utf-8'))

golden = defaultdict(list)
candidates = defaultdict(list)

for b in bugs:
    cat = b['root_cause_category']
    if cat == '需人工判断':
        continue
    score = int(b.get('score', '0'))
    fix = b.get('fix_status', '')
    title = (b.get('title') or '')[:150]
    rc = (b.get('parsed_root_cause') or '')[:250]
    keywords = b.get('matched_keywords', '')
    
    entry = {'bug_id': b['bug_id'], 'title': title, 'root_cause': rc, 'keywords': keywords, 'score': score}
    
    if score >= 6 and '已修复' in fix:
        golden[cat].append(entry)
    elif score >= 3:
        candidates[cat].append(entry)

result = {}
for cat in sorted(set(list(golden.keys()) + list(candidates.keys()))):
    picks = golden.get(cat, [])[:3]
    if len(picks) < 2:
        existing_ids = {p['bug_id'] for p in picks}
        extra = [c for c in candidates.get(cat, []) if c['bug_id'] not in existing_ids]
        picks += extra[:2 - len(picks)]
    if picks:
        result[cat] = picks

Path('outputs/golden_examples.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

all_cats = {r['name'] for r in FINE_GRAINED_RULES}
print(f"覆盖: {len(result)}/25")
print(f"缺失: {all_cats - set(result.keys())}")
print(f"示例总数: {sum(len(v) for v in result.values())}")
print("SAVED")
