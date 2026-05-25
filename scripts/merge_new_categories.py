#!/usr/bin/env python
"""合并新分类建议到 FINE_GRAINED_RULES

用法:
  uv run python scripts/merge_new_categories.py          # 交互式确认
  uv run python scripts/merge_new_categories.py --auto   # 自动合并全部
  uv run python scripts/merge_new_categories.py --dry-run # 预览
"""

import argparse
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PENDING_PATH = BASE_DIR / "outputs" / "pending_categories.json"
MODELS_PATH = BASE_DIR / "src" / "my_crew" / "models.py"


def parse_section_from_name(name: str) -> str:
    """从分类名提取领域→section"""
    parts = name.split("-")
    if len(parts) >= 1:
        domain = parts[0]
        if domain in ("硬件", "系统", "环境", "场景", "QNX", "应用crash"):
            return f"一、{domain}相关"
    return "一、未分类"


def generate_keywords(name: str, bugs: list[str]) -> dict:
    """从分类名自动生成关键词弱匹配"""
    keywords = {"strong": [], "medium": [], "weak": []}
    # 提取名称中的关键词
    for part in name.replace("/", " ").replace("-", " ").split():
        if len(part) >= 2 and not part.isdigit():
            keywords["weak"].append(part.lower())
    return keywords


def main():
    parser = argparse.ArgumentParser(description="合并 LLM 提出的新分类到规则库")
    parser.add_argument("--auto", action="store_true", help="自动合并全部建议")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改")
    args = parser.parse_args()

    if not PENDING_PATH.exists():
        print("📭 没有待确认的新分类建议")
        return

    pending = json.loads(PENDING_PATH.read_text(encoding="utf-8"))
    print(f"📋 共 {len(pending)} 个待确认新分类:\n")

    for i, (cat, bids) in enumerate(pending.items(), 1):
        print(f"  [{i}] {cat}  ({len(bids)} 条Bug)")
        for bid in bids[:5]:
            print(f"       {bid}")
        if len(bids) > 5:
            print(f"       ... 还有 {len(bids)-5} 条")
        print()

    if args.dry_run:
        print("🔍 DRY RUN — 未修改任何文件")
        return

    if not args.auto:
        response = input("确认合并以上所有分类? (y/N): ").strip().lower()
        if response != "y":
            # 逐个确认
            confirmed = {}
            for cat, bids in pending.items():
                r = input(f"  合并「{cat}」({len(bids)}条)? (y/N): ").strip().lower()
                if r == "y":
                    confirmed[cat] = bids
            pending = confirmed
        if not pending:
            print("已取消")
            return

    # 读取 models.py
    content = MODELS_PATH.read_text(encoding="utf-8")
    
    added = 0
    for cat, bids in pending.items():
        # 检查是否已存在
        if f'"name": "{cat}"' in content:
            print(f"  ⚠️ 已存在: {cat}，跳过")
            continue
        
        # 生成 section
        section = parse_section_from_name(cat)
        keywords = generate_keywords(cat, bids)
        
        # 找到插入位置（FINE_GRAINED_RULES 最后一条规则末尾）
        marker = '        "section": "一、'
        # 找最后一个 section 行
        last_section_idx = content.rfind(marker)
        if last_section_idx < 0:
            print("  ❌ 找不到 FINE_GRAINED_RULES 结尾")
            continue
        
        # 找到最后一个 }, 的位置（在 ] 之前），插入新规则
        bracket_idx = content.rfind("]", last_section_idx)
        if bracket_idx < 0:
            print("  ❌ 找不到列表闭合")
            continue
        
        # 往前找最后一个 },
        close_idx = content.rfind("},", last_section_idx, bracket_idx)
        if close_idx < 0:
            close_idx = content.rfind("}", last_section_idx, bracket_idx)
        if close_idx < 0:
            print("  ❌ 找不到插入点")
            continue
        close_idx += 1 if content[close_idx] == "}" else 2  # 跳过 } 或 },
        
        new_rule = f"\n    {{{{\n        \"name\": \"{cat}\",\n        \"description\": \"LLM自动发现的新分类（{len(bids)}条Bug）\",\n        \"keywords\": {json.dumps(keywords, indent=12, ensure_ascii=False)},\n        \"exclude_keywords\": [],\n        \"priority\": 50,\n        \"section\": \"{section}\",\n    }},\n"
        
        content = content[:close_idx] + new_rule + content[close_idx:]
        added += 1
        print(f"  ✅ 已添加: {cat}")

    if added > 0:
        MODELS_PATH.write_text(content, encoding="utf-8")
        print(f"\n✅ 已合并 {added} 个新分类到 {MODELS_PATH}")
        print(f"   请验证后运行: uv run python -c 'from my_crew.models import FINE_GRAINED_RULES; print(len(FINE_GRAINED_RULES))'")
        
        # 清空 pending
        PENDING_PATH.write_text("{}", encoding="utf-8")
        print(f"   已清空 {PENDING_PATH}")
    else:
        print("\n   (无新增分类)")


if __name__ == "__main__":
    main()
