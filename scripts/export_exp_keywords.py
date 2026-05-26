#!/usr/bin/env python
"""断链1修复: experience.db → keywords_override.json 反哺通道

从经验库 API 导出高置信度经验的关键词，写入
outputs/keywords_override.json，由 models.py 的
_OVERRIDE_PATH 在下一次分类时自动合并生效。

触发条件（任意一种）:
  - main.py 工作流一结束后自动调用
  - 手动: uv run python scripts/export_exp_keywords.py
  - 参数: --min-confidence 0.7 --min-hits 2

过滤规则:
  - confidence >= MIN_CONFIDENCE (默认 0.7)
  - hit_count  >= MIN_HITS       (默认 2)
  - 中/低置信度且词频<2 的条目跳过
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = BASE_DIR / "outputs" / "keywords_override.json"
API_URL = os.environ.get("EXPERIENCE_API_URL", "http://10.219.9.92:8765")


def fetch_experiences(api_url: str, min_confidence: float, min_hits: int) -> list:
    """从 API 获取经验列表，带过滤。"""
    url = f"{api_url}/experience"
    try:
        resp = requests.get(url, params={"min_confidence": min_confidence, "min_hits": min_hits}, timeout=10)
        resp.raise_for_status()
        return resp.json().get("experiences", [])
    except requests.exceptions.ConnectionError:
        print(f"[export_exp_keywords] ⚠️  无法连接 {url}，跳过关键词反哺")
        return []
    except Exception as e:
        print(f"[export_exp_keywords] ❌ 获取经验失败: {e}")
        return []


def build_override(experiences: list) -> dict:
    """
    将经验列表转为 keywords_override.json 格式:
    {
      "分类名": {
        "strong":  [...],   # 来自 experience.keywords (高置信度 >= 0.85)
        "medium":  [...],   # 置信度 0.7-0.85
        "weak":    [...]    # 仅用来提权，不覆盖原始规则
      }
    }
    models.py _merge_override() 在合并时会叠加到现有规则上。
    """
    override: dict[str, dict] = {}

    for exp in experiences:
        cat = exp.get("category", "").strip()
        if not cat:
            continue
        raw_kws = exp.get("keywords", [])
        if isinstance(raw_kws, str):
            try:
                raw_kws = json.loads(raw_kws)
            except Exception:
                raw_kws = [raw_kws]
        if not raw_kws:
            continue

        confidence = float(exp.get("confidence", 0.5))
        # 按置信度分级
        if confidence >= 0.85:
            level = "strong"
        elif confidence >= 0.7:
            level = "medium"
        else:
            level = "weak"

        entry = override.setdefault(cat, {"strong": [], "medium": [], "weak": []})
        for kw in raw_kws:
            kw = str(kw).strip()
            if kw and kw not in entry[level]:
                entry[level].append(kw)

    return override


def merge_with_existing(existing: dict, new_data: dict) -> dict:
    """合并到已有 override 文件，不丢失人工添加的词。"""
    merged = dict(existing)
    for cat, levels in new_data.items():
        if cat not in merged:
            merged[cat] = {"strong": [], "medium": [], "weak": []}
        for level in ("strong", "medium", "weak"):
            existing_kws = set(merged[cat].get(level, []))
            for kw in levels.get(level, []):
                if kw not in existing_kws:
                    merged[cat][level].append(kw)
                    existing_kws.add(kw)
    return merged


def main():
    parser = argparse.ArgumentParser(description="经验库 → keywords_override.json 反哺")
    parser.add_argument("--min-confidence", type=float, default=0.7, help="最低置信度（默认0.7）")
    parser.add_argument("--min-hits", type=int, default=2, help="最低命中次数（默认2）")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写文件")
    args = parser.parse_args()

    print(f"[export_exp_keywords] 从 {API_URL}/experience 拉取经验...")
    experiences = fetch_experiences(API_URL, args.min_confidence, args.min_hits)

    if not experiences:
        print("[export_exp_keywords] 无符合条件的经验，跳过")
        return

    new_override = build_override(experiences)
    print(f"[export_exp_keywords] 覆盖分类数: {len(new_override)}")
    for cat, levels in new_override.items():
        total = sum(len(v) for v in levels.values())
        print(f"   {cat}: strong={len(levels['strong'])} medium={len(levels['medium'])} weak={len(levels['weak'])} (共{total}词)")

    # 合并到已有文件
    existing = {}
    if OUTPUT_PATH.exists():
        try:
            existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    merged = merge_with_existing(existing, new_override)

    if args.dry_run:
        print(f"\n[DRY RUN] 预览写入内容 → {OUTPUT_PATH}")
        print(json.dumps(merged, ensure_ascii=False, indent=2)[:2000])
        return

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 已写入 {OUTPUT_PATH}（{len(merged)} 个分类，下次运行工作流一时自动生效）")


if __name__ == "__main__":
    main()
