#!/usr/bin/env python
"""将 classification_data.json 转换为交互式 HTML 看板

用法:
  uv run python scripts/json_to_dashboard.py
  uv run python scripts/json_to_dashboard.py --open

功能:
  - 汇总数据卡片（总数/分类数/模块数/需人工判断数）
  - 分类分布条形图
  - 25类可排序/可搜索/可筛选表格
  - 修复状态切换（已修复/未修复/无法复现）
  - 导出 CSV
"""

import argparse
import json
import sys
from collections import Counter
from html import escape
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_JSON = BASE_DIR / "outputs" / "classification_data.json"
DEFAULT_OUTPUT = BASE_DIR / "outputs" / "classification_dashboard.html"


def load_data(json_path: Path) -> list[dict]:
    if not json_path.exists():
        print(f"[错误] 找不到 JSON 文件: {json_path}", file=sys.stderr)
        sys.exit(1)
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def compute_stats(bugs: list[dict]) -> dict:
    total = len(bugs)
    cat_counter = Counter(b.get("root_cause_category", "未分类") for b in bugs)
    fix_counter = Counter(b.get("fix_status", "未知") for b in bugs)
    mod_counter = Counter(b.get("module", "未知") for b in bugs)
    sev_counter = Counter(b.get("severity", "未知") for b in bugs)

    manual = sum(1 for b in bugs if b.get("root_cause_category") == "需人工判断")
    has_root_cause = sum(1 for b in bugs if b.get("parsed_root_cause", "").strip())
    has_fix = sum(1 for b in bugs if b.get("parsed_fix_method", "").strip())

    return {
        "total": total,
        "categories": len(cat_counter),
        "modules": len(mod_counter),
        "manual": manual,
        "manual_pct": round(manual / total * 100, 1) if total else 0,
        "has_root_cause": has_root_cause,
        "root_cause_pct": round(has_root_cause / total * 100, 1) if total else 0,
        "has_fix": has_fix,
        "fix_pct": round(has_fix / total * 100, 1) if total else 0,
        "categories_sorted": cat_counter.most_common(),
        "fix_status": fix_counter.most_common(),
        "severity": sev_counter.most_common(),
    }


def generate_html(bugs: list[dict], stats: dict) -> str:
    s = stats
    # Build per-category bug tables
    cat_groups: dict[str, list[dict]] = {}
    for b in bugs:
        cat = b.get("root_cause_category", "未分类") or "未分类"
        cat_groups.setdefault(cat, []).append(b)

    cat_tables_html = ""
    for cat, bugs_in_cat in sorted(cat_groups.items(),
                                    key=lambda x: len(x[1]), reverse=True):
        rows = ""
        for b in bugs_in_cat:
            bid = escape(b.get("bug_id", "无") or "无")
            title = escape(b.get("title", "无") or "无")[:120]
            rc = escape(b.get("parsed_root_cause", "") or "")[:200]
            fix = escape(b.get("parsed_fix_method", "") or "")[:200]
            status = escape(b.get("status", "") or "")
            severity = escape(b.get("severity", "") or "")
            module = escape(b.get("module", "") or "")
            keywords = escape(b.get("matched_keywords", "") or "")
            fix_st = escape(b.get("fix_status", "") or "")

            row_class = ""
            if fix_st == "未修复/挂起":
                row_class = ' class="row-pending"'
            elif fix_st == "无法复现":
                row_class = ' class="row-unrepro"'

            rows += f"""<tr{row_class}>
                <td class="c-bid">{bid}</td>
                <td class="c-title">{title}</td>
                <td class="c-cat">{cat}</td>
                <td class="c-status">{status}</td>
                <td class="c-sev">{severity}</td>
                <td class="c-mod">{module}</td>
                <td class="c-fix">{fix_st}</td>
                <td class="c-rc">{rc}</td>
                <td class="c-key">{keywords}</td>
            </tr>"""

        cat_tables_html += f"""<div class="cat-section">
            <h3 onclick="toggleCat(this)">{escape(cat)}
                <span class="cat-count">{len(bugs_in_cat)} 条</span>
                <span class="toggle-icon">▼</span>
            </h3>
            <div class="cat-body">
                <table>
                    <thead><tr>
                        <th>Bug ID</th><th>Title</th><th>分类</th>
                        <th>Status</th><th>Severity</th><th>Module</th>
                        <th>修复状态</th><th>根因</th><th>关键词</th>
                    </tr></thead>
                    <tbody>{rows}</tbody>
                </table>
            </div>
        </div>"""

    # Category distribution chart data
    chart_labels = json.dumps([c for c, n in s["categories_sorted"][:15]])
    chart_values = json.dumps([n for c, n in s["categories_sorted"][:15]])

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>黑卡闪问题分类看板</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:2rem}}
h1{{font-size:1.5rem;margin-bottom:.5rem;color:#f0f6fc}}
.subtitle{{color:#8b949e;margin-bottom:2rem;font-size:.875rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:1rem;margin-bottom:2rem}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.25rem;text-align:center}}
.card .num{{font-size:2rem;font-weight:700;color:#58a6ff}}
.card .num.warn{{color:#f85149}}
.card .num.ok{{color:#3fb950}}
.card .label{{color:#8b949e;font-size:.75rem;margin-top:.25rem}}
.chart-box{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.25rem;margin-bottom:2rem;overflow-x:auto}}
.filter-bar{{display:flex;gap:1rem;margin-bottom:1rem;flex-wrap:wrap}}
.filter-bar input,.filter-bar select{{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:.5rem .75rem;color:#e6edf3;font-size:.875rem}}
.filter-bar input{{flex:1;min-width:200px}}
.filter-bar select{{cursor:pointer}}
.cat-section{{background:#161b22;border:1px solid #30363d;border-radius:8px;margin-bottom:1rem;overflow:hidden}}
.cat-section h3{{padding:.75rem 1rem;cursor:pointer;font-size:.875rem;display:flex;align-items:center;gap:.5rem;user-select:none}}
.cat-section h3:hover{{background:#1c2128}}
.cat-count{{background:#1f6feb33;color:#58a6ff;padding:.125rem .5rem;border-radius:10px;font-size:.75rem}}
.toggle-icon{{margin-left:auto;font-size:.75rem;transition:transform .2s}}
.cat-body{{overflow-x:auto;padding:0 0 1rem 0}}
.cat-body.closed{{display:none}}
table{{width:100%;border-collapse:collapse;font-size:.8125rem}}
th{{text-align:left;padding:.5rem 1rem;border-bottom:1px solid #30363d;color:#8b949e;font-weight:600;white-space:nowrap;cursor:pointer;position:relative}}
th:hover{{color:#58a6ff}}
td{{padding:.375rem 1rem;border-bottom:1px solid #21262d;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
tr:hover{{background:#1c2128}}
tr.row-pending{{background:#3d1f0033}}
tr.row-unrepro{{background:#1f3d1f33}}
.c-bid{{color:#58a6ff;font-family:monospace;font-size:.75rem}}
.c-title{{max-width:350px}}
.c-cat{{color:#d2a8ff;font-size:.75rem}}
.c-fix{{font-weight:600}}
.c-key{{color:#8b949e;font-size:.75rem;max-width:150px}}
.legend{{display:flex;gap:1.5rem;margin-bottom:1rem;font-size:.75rem;color:#8b949e}}
.dot{{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:4px;vertical-align:middle}}
.dot-fixed{{background:#3fb950}}
.dot-pending{{background:#d29922}}
.dot-unrepro{{background:#8b949e}}
.controls{{display:flex;gap:1rem;align-items:center;margin-bottom:1rem;flex-wrap:wrap}}
.controls button{{background:#21262d;border:1px solid #30363d;border-radius:6px;padding:.4rem .8rem;color:#e6edf3;cursor:pointer;font-size:.8125rem}}
.controls button:hover{{background:#30363d}}
.bar{{display:flex;height:200px;align-items:flex-end;gap:4px;padding:.5rem 0}}
.bar-item{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;min-width:30px}}
.bar-fill{{width:100%;background:linear-gradient(180deg,#1f6feb,#58a6ff);border-radius:4px 4px 0 0;min-height:4px;transition:height .3s}}
.bar-label{{font-size:.6rem;color:#8b949e;margin-top:4px;writing-mode:vertical-lr;text-orientation:mixed;max-height:60px;overflow:hidden}}
</style>
</head>
<body>
<h1>📊 黑卡闪问题分类看板</h1>
<p class="subtitle">数据来源: classification_data.json · 共 {s["total"]} 条 Bug · {s["categories"]} 个分类 · {s["modules"]} 个模块</p>

<div class="cards">
    <div class="card"><div class="num">{s["total"]}</div><div class="label">Bug 总数</div></div>
    <div class="card"><div class="num">{s["categories"]}</div><div class="label">分类数 (25类)</div></div>
    <div class="card"><div class="num">{s["modules"]}</div><div class="label">模块数</div></div>
    <div class="card"><div class="num warn">{s["manual"]}</div><div class="label">需人工判断 ({s["manual_pct"]}%)</div></div>
    <div class="card"><div class="num">{s["has_root_cause"]}</div><div class="label">有根因记录 ({s["root_cause_pct"]}%)</div></div>
    <div class="card"><div class="num">{s["has_fix"]}</div><div class="label">有修复方式 ({s["fix_pct"]}%)</div></div>
</div>

<div class="chart-box">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
        <h3 style="font-size:.875rem">分类分布 (Top 15)</h3>
        <span style="color:#8b949e;font-size:.75rem">{s["total"]} total</span>
    </div>
    <div class="bar" id="chart">正在渲染...</div>
</div>

<div class="legend">
    <span><span class="dot dot-fixed"></span>已修复</span>
    <span><span class="dot dot-pending"></span>未修复/挂起</span>
    <span><span class="dot dot-unrepro"></span>无法复现</span>
</div>

<div class="controls">
    <input type="text" id="search" placeholder="搜索 Bug ID / Title / 关键词..." oninput="filterTable()">
    <select id="catFilter" onchange="filterTable()">
        <option value="">所有分类</option>
        {"".join(f'<option value="{escape(c)}">{escape(c)} ({n})</option>' for c, n in s["categories_sorted"])}
    </select>
    <select id="fixFilter" onchange="filterTable()">
        <option value="">所有修复状态</option>
        <option value="已修复">已修复</option>
        <option value="未修复/挂起">未修复/挂起</option>
        <option value="无法复现">无法复现</option>
    </select>
    <select id="sevFilter" onchange="filterTable()">
        <option value="">所有 Severity</option>
        {"".join(f'<option value="{escape(v)}">{escape(v)} ({n})</option>' for v, n in s["severity"])}
    </select>
    <button onclick="expandAll()">展开全部</button>
    <button onclick="collapseAll()">收起全部</button>
    <button onclick="exportCSV()">导出 CSV</button>
</div>

<div id="bugList">{cat_tables_html}</div>

<script>
// 🌟 Bar chart
(function(){{
    var labels = {chart_labels};
    var values = {chart_values};
    var maxVal = Math.max(...values, 1);
    var bar = document.getElementById('chart');
    bar.innerHTML = labels.map(function(l,i){{
        var pct = (values[i]/maxVal*100);
        return '<div class="bar-item" title="'+l+': '+values[i]+'条"><div class="bar-fill" style="height:'+pct+'%"></div><div class="bar-label">'+l.split('-').pop()+'</div></div>';
    }}).join('');
}})();

// 🔍 Filter
function filterTable(){{
    var q = document.getElementById('search').value.toLowerCase();
    var cat = document.getElementById('catFilter').value;
    var fix = document.getElementById('fixFilter').value;
    var sev = document.getElementById('sevFilter').value;
    var rows = document.querySelectorAll('#bugList tbody tr');
    rows.forEach(function(r){{
        var text = (r.textContent||'').toLowerCase();
        var rCat = (r.querySelector('.c-cat')||{{}}).textContent||'';
        var rFix = (r.querySelector('.c-fix')||{{}}).textContent||'';
        var rSev = (r.querySelector('.c-sev')||{{}}).textContent||'';
        var match = (!q||text.includes(q)) && (!cat||rCat===cat) && (!fix||rFix===fix) && (!sev||rSev===sev);
        r.style.display = match ? '' : 'none';
    }});
    // Show/hide cat sections
    document.querySelectorAll('.cat-section').forEach(function(s){{
        var vis = Array.from(s.querySelectorAll('tbody tr')).some(function(r){{return r.style.display!=='none'}});
        if(!vis) s.style.display='none'; else s.style.display='';
    }});
}}

// Toggle category
function toggleCat(el){{
    var body = el.nextElementSibling;
    body.classList.toggle('closed');
    el.querySelector('.toggle-icon').textContent = body.classList.contains('closed') ? '▶' : '▼';
}}

function expandAll(){{ document.querySelectorAll('.cat-body').forEach(function(b){{b.classList.remove('closed');}});
    document.querySelectorAll('.toggle-icon').forEach(function(i){{i.textContent='▼';}}); }}
function collapseAll(){{ document.querySelectorAll('.cat-body').forEach(function(b){{b.classList.add('closed');}});
    document.querySelectorAll('.toggle-icon').forEach(function(i){{i.textContent='▶';}}); }}

// 📤 CSV Export
function exportCSV(){{
    var rows = [['Bug ID','Title','Root Cause Category','Status','Severity','Module','Fix Status','Root Cause','Fix Method','Keywords']];
    document.querySelectorAll('tbody tr').forEach(function(r){{
        rows.push([
            (r.querySelector('.c-bid')||{{}}).textContent||'',
            (r.querySelector('.c-title')||{{}}).textContent||'',
            (r.querySelector('.c-cat')||{{}}).textContent||'',
            (r.querySelector('.c-status')||{{}}).textContent||'',
            (r.querySelector('.c-sev')||{{}}).textContent||'',
            (r.querySelector('.c-mod')||{{}}).textContent||'',
            (r.querySelector('.c-fix')||{{}}).textContent||'',
            (r.querySelector('.c-rc')||{{}}).textContent||'',
            (r.querySelector('.c-key')||{{}}).textContent||'',
        ]);
    }});
    var csv = rows.map(function(r){{return r.map(function(v){{return '"'+v.replace(/"/g,'""')+'"'}}).join(',')}}).join('\\n');
    var blob = new Blob(['\\ufeff'+csv],{{type:'text/csv;charset=utf-8;'}});
    var a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='classification_data.csv'; a.click();
}}
</script>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="JSON → HTML 看板")
    parser.add_argument("--json", default=str(DEFAULT_JSON))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--open", action="store_true", help="完成后在浏览器打开")
    args = parser.parse_args()

    bugs = load_data(Path(args.json))
    stats = compute_stats(bugs)
    html = generate_html(bugs, stats)
    out_path = Path(args.output)
    out_path.write_text(html, encoding="utf-8")

    print(f"[DASHBOARD] 看板已生成: {out_path}")
    print(f"           Bug 总数: {stats['total']}")
    print(f"           分类数: {stats['categories']} / 模块数: {stats['modules']}")
    print(f"           需人工判断: {stats['manual']} ({stats['manual_pct']}%)")
    print(f"           有根因记录: {stats['has_root_cause']} / 有修复方式: {stats['has_fix']}")
    print(f"           文件大小: {len(html):,} bytes")

    if args.open:
        import subprocess, webbrowser
        webbrowser.open(out_path.resolve().as_uri())


if __name__ == "__main__":
    main()
