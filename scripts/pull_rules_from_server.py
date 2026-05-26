#!/usr/bin/env python
"""断链5修复: 服务器 category_rules → 本地 rules_override.json 同步

从经验库 API 的 /rules 端点拉取已审核的分类规则，
写入本地 outputs/rules_override.json，
merge_new_categories.py 在合并新分类后也会调用此脚本刷新。

用法:
  uv run python scripts/pull_rules_from_server.py          # 拉取全部规则
  uv run python scripts/pull_rules_from_server.py --push   # 将本地 models.py 规则推送到服务器
  uv run python scripts/pull_rules_from_server.py --dry-run
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
RULES_OVERRIDE_PATH = BASE_DIR / "outputs" / "rules_override.json"
MODELS_PATH = BASE_DIR / "src" / "my_crew" / "models.py"
API_URL = os.environ.get("EXPERIENCE_API_URL", "http://10.219.9.92:8765")


def pull_rules(api_url: str) -> list:
    """GET /rules → 返回规则列表"""
    url = f"{api_url}/rules"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json().get("rules", [])
    except requests.exceptions.ConnectionError:
        print(f"[pull_rules] ⚠️  无法连接 {url}")
        return []
    except Exception as e:
        print(f"[pull_rules] ❌ 拉取失败: {e}")
        return []


def push_rule(api_url: str, rule: dict) -> bool:
    """POST /rules → 将本地规则推送到服务器"""
    url = f"{api_url}/rules"
    try:
        resp = requests.post(url, json=rule, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[push_rule] ❌ 推送失败 {rule.get('name')}: {e}")
        return False


def extract_rules_from_models() -> list:
    """从 models.py 的 FINE_GRAINED_RULES 中提取规则（简单文本解析）"""
    import re
    content = MODELS_PATH.read_text(encoding="utf-8")
    # 找 FINE_GRAINED_RULES = [ ... ] 的内容
    m = re.search(r'FINE_GRAINED_RULES\s*=\s*\[(.+?)\n\]', content, re.DOTALL)
    if not m:
        print("[extract_rules] ❌ 找不到 FINE_GRAINED_RULES")
        return []

    rules = []
    # 逐个提取 name
    for name_match in re.finditer(r'"name"\s*:\s*"([^"]+)"', m.group(1)):
        rules.append({"name": name_match.group(1), "source": "local_models"})
    return rules


def main():
    parser = argparse.ArgumentParser(description="服务器规则库 ↔ 本地同步")
    parser.add_argument("--push", action="store_true", help="将本地规则推送到服务器（不覆盖已有）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    args = parser.parse_args()

    if args.push:
        # 推送本地规则到服务器
        local_rules = extract_rules_from_models()
        print(f"[pull_rules] 推送本地 {len(local_rules)} 条规则到 {API_URL}/rules ...")
        ok = 0
        for rule in local_rules:
            if push_rule(API_URL, rule):
                ok += 1
        print(f"✅ 推送完成: {ok}/{len(local_rules)} 条成功")
        return

    # 拉取服务器规则
    print(f"[pull_rules] 从 {API_URL}/rules 拉取规则...")
    rules = pull_rules(API_URL)

    if not rules:
        print("[pull_rules] 无规则数据，跳过")
        return

    print(f"[pull_rules] 获取到 {len(rules)} 条规则")
    for r in rules[:5]:
        print(f"   {r.get('name')} | 来源:{r.get('source','?')} | 状态:{r.get('status','?')}")
    if len(rules) > 5:
        print(f"   ... 还有 {len(rules)-5} 条")

    if args.dry_run:
        print(f"\n[DRY RUN] 预览写入 → {RULES_OVERRIDE_PATH}")
        return

    RULES_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_OVERRIDE_PATH.write_text(
        json.dumps({"rules": rules, "_from": f"{API_URL}/rules"}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n✅ 已写入 {RULES_OVERRIDE_PATH}")
    print(f"   merge_new_categories.py 下次运行时会参考此文件避免重复添加规则")


if __name__ == "__main__":
    main()
