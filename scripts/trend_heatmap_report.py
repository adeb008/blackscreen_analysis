#!/usr/bin/env python
"""趋势与热力图报告 — 从 analyzed_bugs.json 的历史快照生成

用法:
  uv run python scripts/trend_heatmap_report.py
  uv run python scripts/trend_heatmap_report.py --open

输出:
  outputs/trend_heatmap_report.html  — 自包含的 HTML 报告
"""

import argparse
import json
import sys
from collections import Counter
from html import escape
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_KB = BASE_DIR / "black_screen_data" / "analyzed_bugs.json"
DEFAULT_OUTPUT = BASE_DIR / "outputs" / "trend_heatmap_report.html"


def load_kb(kb_path: Path) -> dict:
    if not kb_path.exists():
        print(f"[错误] 找不到知识库: {kb_path}", file=sys.stderr)
        sys.exit(1)
    with open(kb_path, encoding="utf-8") as f:
        return json.load(f)


def generate_html(kb: dict) -> str:
    meta = kb.get("_meta", {})
    history = meta.get("run_history", [])
    bugs = kb.get("bugs", {})
    total = len(bugs)

    # ── 当前统计数据 ──
    cat_counter = Counter(b.get("category", "未分类") for b in bugs.values())
    mod_counter = Counter(b.get("module", "未知") for b in bugs.values())
    fix_counter = Counter(b.get("fix_status", "未知") for b in bugs.values())
    sev_counter = Counter(b.get("severity", "未知") for b in bugs.values())
    top_cats = cat_counter.most_common(20)
    top_mods = mod_counter.most_common(15)

    # ── 历史趋势数据 ──
    # 所有出现过的分类
    all_cats = set()
    for snap in history:
        all_cats.update(snap.get("categories", {}).keys())
    all_cats = sorted(all_cats)
    # 时间戳
    timestamps = [snap["timestamp"][:16] for snap in history]
    # 趋势数据: 每个分类每轮的数量
    trend_data = {}
    for cat in all_cats:
        trend_data[cat] = [snap.get("categories", {}).get(cat, 0) for snap in history]

    # 模块热力图数据 (当前)
    heatmap_labels = json.dumps([m for m, c in top_mods])
    heatmap_values = json.dumps([c for m, c in top_mods])

    # 分类分布
    cat_labels = json.dumps([c for c, n in top_cats])
    cat_values = json.dumps([n for c, n in top_cats])

    # 修复状态
    fix_labels = json.dumps([s for s, n in fix_counter.most_common()])
    fix_values = json.dumps([n for s, n in fix_counter.most_common()])
    fix_colors = json.dumps([
        "#3fb950" if s == "已修复" else
        "#d29922" if "挂起" in s or "未修复" in s else
        "#8b949e"
        for s, n in fix_counter.most_common()
    ])

    # 历史趋势（仅 Top 10 分类绘制折线）
    trend_labels = json.dumps(timestamps)
    trend_lines = json.dumps([
        {"label": cat, "data": vals[:len(timestamps)]}
        for cat, vals in sorted(trend_data.items(), key=lambda x: -sum(x[1]))[:10]
    ])

    # 热力图矩阵：分类×修复状态
    heat_cats = [c for c, n in top_cats[:10]]
    heat_statuses = ["已修复", "未修复/挂起", "无法复现"]
    heat_matrix = {}
    for c in heat_cats:
        inner = {}
        for s in heat_statuses:
            inner[s] = sum(
                1 for b in bugs.values()
                if b.get("category") == c and b.get("fix_status") == s
            )
        heat_matrix[c] = inner

    has_history = len(history) >= 2

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>黑卡闪分析 · 趋势与热力图</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,'Segoe UI',sans-serif;background:#0d1117;color:#e6edf3;padding:2rem}}
h1{{font-size:1.5rem;margin-bottom:.3rem;color:#f0f6fc}}
.subtitle{{color:#8b949e;margin-bottom:2rem;font-size:.875rem}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1rem;margin-bottom:2rem}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.25rem;text-align:center}}
.card .num{{font-size:2rem;font-weight:700;color:#58a6ff}}
.card .num.warn{{color:#f85149}}
.card .num.ok{{color:#3fb950}}
.card .num.orange{{color:#d29922}}
.card .label{{color:#8b949e;font-size:.75rem;margin-top:.25rem}}
.section{{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1.5rem;margin-bottom:1.5rem}}
.section h2{{font-size:1rem;margin-bottom:1.25rem;color:#f0f6fc;border-left:3px solid #58a6ff;padding-left:.75rem}}
.section h2.green{{border-color:#3fb950}}
.section h2.orange{{border-color:#d29922}}
.section h2.purple{{border-color:#a78bfa}}
.chart-container{{width:100%;overflow-x:auto;padding:.5rem 0}}
.bar-chart{{display:flex;height:220px;align-items:flex-end;gap:4px;padding:.5rem 0;min-width:400px}}
.bar-item{{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;min-width:30px}}
.bar-fill{{width:80%;border-radius:4px 4px 0 0;min-height:4px;transition:height .3s;position:relative}}
.bar-fill:hover{{opacity:.8}}
.bar-fill.blue{{background:linear-gradient(180deg,#1f6feb,#58a6ff)}}
.bar-fill.green{{background:linear-gradient(180deg,#2ea043,#3fb950)}}
.bar-fill.orange{{background:linear-gradient(180deg,#9e6a03,#d29922)}}
.bar-fill.gray{{background:linear-gradient(180deg,#484f58,#8b949e)}}
.bar-label{{font-size:.6rem;color:#8b949e;margin-top:4px;writing-mode:vertical-lr;text-orientation:mixed;max-height:50px;overflow:hidden}}
.bar-val{{font-size:.65rem;color:#e6edf3;margin-bottom:2px}}
.trend-chart{{min-width:600px;height:250px;position:relative;margin-top:1rem}}
.trend-chart svg{{width:100%;height:100%}}
.heatmap-grid{{display:grid;gap:2px;min-width:300px}}
.heatmap-row{{display:grid;grid-template-columns:100px repeat(4,1fr);gap:2px;align-items:center}}
.heatmap-header{{font-size:.7rem;color:#8b949e;text-align:center;padding:4px}}
.heatmap-label{{font-size:.75rem;color:#e6edf3;padding:2px 4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.heatmap-cell{{text-align:center;padding:6px 4px;font-size:.75rem;border-radius:3px;min-height:30px;display:flex;align-items:center;justify-content:center}}
.heatmap-legend{{display:flex;gap:.5rem;margin-top:.75rem;align-items:center;font-size:.75rem;color:#8b949e}}
.heatmap-legend .hm-block{{width:20px;height:16px;border-radius:2px}}
.footer{{text-align:center;margin-top:1.5rem;color:#475569;font-size:.75rem}}
.note{{color:#8b949e;font-size:.875rem;padding:1rem;background:#0d1117;border:1px solid #30363d;border-radius:6px;margin-bottom:1rem}}
</style>
</head>
<body>

<h1>📈 黑卡闪分析 · 趋势与热力图</h1>
<p class="subtitle">数据来源: {escape(meta.get("source_file", "未知"))} · 更新时间: {escape(meta.get("last_run", "未知"))} · 历史轮次: {len(history)} 轮</p>

<div class="cards">
    <div class="card"><div class="num">{total}</div><div class="label">Bug 总量</div></div>
    <div class="card"><div class="num">{len(cat_counter)}</div><div class="label">分类数</div></div>
    <div class="card"><div class="num">{len(mod_counter)}</div><div class="label">模块数</div></div>
    <div class="card"><div class="num warn">{cat_counter.get("需人工判断", 0)}</div><div class="label">需人工判断</div></div>
    <div class="card"><div class="num ok">{fix_counter.get("已修复", 0)}</div><div class="label">已修复</div></div>
    <div class="card"><div class="num orange">{fix_counter.get("未修复/挂起", 0)}</div><div class="label">未修复/挂起</div></div>
</div>

<!-- 分类分布 -->
<div class="section">
<h2>📊 分类分布 Top 20</h2>
<div class="chart-container">
    <div class="bar-chart" id="catChart">渲染中...</div>
</div>
</div>

<!-- 修复状态 -->
<div class="section">
<h2 class="green">✅ 修复状态分布</h2>
<div class="chart-container">
    <div class="bar-chart" id="fixChart" style="height:180px">渲染中...</div>
</div>
</div>

<!-- Severity -->
<div class="section">
<h2 class="orange">⚠️ Severity 分布</h2>
<div class="chart-container">
    <div class="bar-chart" id="sevChart" style="height:180px">渲染中...</div>
</div>
</div>

<!-- 模块热力图 -->
<div class="section">
<h2 class="purple">🔥 模块热力图 Top 15</h2>
<div class="chart-container">
    <div class="bar-chart" id="modChart">渲染中...</div>
</div>
</div>

<!-- 分类×修复状态热力图 -->
<div class="section">
<h2 class="purple">📋 分类 × 修复状态热力图</h2>
<div class="chart-container">
    <div class="heatmap-grid" id="heatmapGrid">渲染中...</div>
    <div class="heatmap-legend">
        <span class="hm-block" style="background:rgba(63,185,80,0.2)"></span> 少
        <span class="hm-block" style="background:rgba(63,185,80,0.5)"></span>
        <span class="hm-block" style="background:rgba(63,185,80,0.8)"></span>
        <span class="hm-block" style="background:rgb(63,185,80)"></span> 多
        <span style="margin-left:1rem">按修复状态着色 × 深浅代表数量</span>
    </div>
</div>
</div>

<!-- 历史趋势 -->
<div class="section">
<h2>📈 分类数量趋势{'' if has_history else '（不足 2 轮历史数据）'}</h2>
{'<div class="note">需要至少 2 轮运行记录才能显示趋势图。每次运行工作流一会自动记录一轮快照。</div>' if not has_history else f'''
<div class="chart-container">
    <div class="trend-chart" id="trendChart">
        <svg viewBox="0 0 700 250">
            <defs>
                <linearGradient id="gridLine" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#30363d" stop-opacity=".3"/><stop offset="100%" stop-color="#30363d" stop-opacity=".05"/></linearGradient>
            </defs>
            <!-- Grid lines -->
            <line x1="60" y1="30" x2="680" y2="30" stroke="url(#gridLine)" stroke-width="1"/>
            <line x1="60" y1="85" x2="680" y2="85" stroke="url(#gridLine)" stroke-width="1"/>
            <line x1="60" y1="140" x2="680" y2="140" stroke="url(#gridLine)" stroke-width="1"/>
            <line x1="60" y1="195" x2="680" y2="195" stroke="url(#gridLine)" stroke-width="1"/>
            <!-- Y-axis labels -->
            <text x="55" y="34" fill="#8b949e" font-size="9" text-anchor="end">max</text>
            <text x="55" y="143" fill="#8b949e" font-size="9" text-anchor="end">mid</text>
            <text x="55" y="200" fill="#8b949e" font-size="9" text-anchor="end">0</text>
            <!-- Lines rendered inline -->
            {_render_trend_svg(trend_data, timestamps)}
        </svg>
    </div>
    <div style="display:flex;gap:1rem;flex-wrap:wrap;margin-top:.5rem;padding-left:60px">
        {''.join(f'<span style="font-size:.75rem;color:#8b949e"><span style="display:inline-block;width:12px;height:3px;border-radius:2px;margin-right:4px;background:{COLORS[i%len(COLORS)]}"></span>{escape(cat)}</span>' for i, (cat, _) in enumerate(sorted(trend_data.items(), key=lambda x:-sum(x[1]))[:10]))}
    </div>
</div>
'''}
</div>

<p class="footer">黑卡闪分析 · 趋势与热力图 · 自动生成</p>

<script>
// 分类柱状图
(function(){{
    var labels = {cat_labels};
    var values = {cat_values};
    var maxVal = Math.max(...values, 1);
    var el = document.getElementById('catChart');
    var colors = ['#58a6ff','#3fb950','#d29922','#f85149','#a78bfa','#79c0ff','#ff7b72','#3fb950','#d29922','#8b949e','#58a6ff','#f0883e','#db6d28','#e3b341','#a371f7','#58a6ff','#79c0ff','#7ee787','#d2a8ff','#ffa657'];
    el.innerHTML = labels.map(function(l,i){{
        var pct = (values[i]/maxVal*100);
        return '<div class="bar-item" title="'+l+': '+values[i]+'条"><div class="bar-fill blue" style="height:'+pct+'%;background:'+colors[i%colors.length]+'"></div><div class="bar-val">'+values[i]+'</div><div class="bar-label">'+l.split('-').pop()+'</div></div>';
    }}).join('');
}})();

// 修复状态
(function(){{
    var labels = {fix_labels};
    var values = {fix_values};
    var maxVal = Math.max(...values, 1);
    var el = document.getElementById('fixChart');
    el.innerHTML = labels.map(function(l,i){{
        var cl = ['green','orange','gray'][i];
        var pct = (values[i]/maxVal*100);
        return '<div class="bar-item" style="flex:0 0 100px"><div class="bar-fill '+cl+'" style="height:'+pct+'%"></div><div class="bar-val">'+values[i]+'</div><div class="bar-label">'+l+'</div></div>';
    }}).join('');
}})();

// Severity
(function(){{
    var labels = {json.dumps([s for s,n in sev_counter.most_common()])};
    var values = {json.dumps([n for s,n in sev_counter.most_common()])};
    var maxVal = Math.max(...values, 1);
    var el = document.getElementById('sevChart');
    el.innerHTML = labels.map(function(l,i){{
        var cl = l==='A'?'warn':l==='B'?'orange':'gray';
        var pct = (values[i]/maxVal*100);
        return '<div class="bar-item" style="flex:0 0 80px"><div class="bar-fill '+(cl==='warn'?'blue':cl==='orange'?'orange':'gray')+'" style="height:'+pct+'%"></div><div class="bar-val">'+values[i]+'</div><div class="bar-label">'+l+'</div></div>';
    }}).join('');
}})();

// 模块热力图
(function(){{
    var labels = {heatmap_labels};
    var values = {heatmap_values};
    var maxVal = Math.max(...values, 1);
    var el = document.getElementById('modChart');
    el.innerHTML = labels.map(function(l,i){{
        var pct = (values[i]/maxVal*100);
        return '<div class="bar-item" title="'+l+': '+values[i]+'"><div class="bar-fill orange" style="height:'+pct+'%"></div><div class="bar-val">'+values[i]+'</div><div class="bar-label" style="writing-mode:horizontal-tb;max-height:30px">'+l+'</div></div>';
    }}).join('');
}})();

// 分类×修复状态热力图
(function(){{
    var el = document.getElementById('heatmapGrid');
    var cats = {json.dumps(heat_cats)};
    var statuses = {json.dumps(heat_statuses)};
    var matrix = {json.dumps(heat_matrix)};
    var allVals = []; for(var c of cats) for(var s of statuses) allVals.push((matrix[c]||{{}})[s]||0);
    var maxV = Math.max(...allVals, 1);

    var html = '<div class="heatmap-row"><div class="heatmap-label">分类</div>';
    for(var s of statuses) html += '<div class="heatmap-header">'+s+'</div>';
    html += '<div class="heatmap-header">合计</div></div>';

    for(var c of cats) {{
        var row = matrix[c]||{{}};
        var total = statuses.reduce(function(a,s){{return a+(row[s]||0);}},0);
        html += '<div class="heatmap-row"><div class="heatmap-label" title="'+c+'">'+c.split('-').pop()+'</div>';
        for(var s of statuses) {{
            var v = row[s]||0;
            var pct = v/maxV;
            var bg = s==='已修复'?'rgb(63,185,80)':s==='未修复/挂起'?'rgb(210,153,34)':'rgb(139,148,158)';
            var alpha = 0.1 + pct*0.7;
            var cellBg = 'rgba('+(s==='已修复'?'63,185,80':s==='未修复/挂起'?'210,153,34':'139,148,158')+','+alpha+')';
            html += '<div class="heatmap-cell" style="background:'+cellBg+'">'+v+'</div>';
        }}
        html += '<div class="heatmap-cell" style="font-weight:600">'+total+'</div></div>';
    }}
    el.innerHTML = html;
}})();
</script>
</body>
</html>"""


COLORS = [
    "#58a6ff", "#3fb950", "#d29922", "#f85149", "#a78bfa",
    "#79c0ff", "#ff7b72", "#f0883e", "#7ee787", "#d2a8ff",
]


def _render_trend_svg(trend_data: dict, timestamps: list) -> str:
    if not timestamps or len(timestamps) < 2:
        return '<text x="350" y="130" fill="#8b949e" font-size="12" text-anchor="middle">数据不足</text>'

    lines = []
    num_ts = len(timestamps)
    max_val = max(max(vals) for vals in trend_data.values()) if trend_data else 1
    max_val = max(max_val, 1)

    def ts_to_x(i):
        return 60 + (620 / max(num_ts - 1, 1)) * i

    def val_to_y(v):
        return 30 + (175 * (1 - v / max_val))

    # 排序取 Top 10
    sorted_items = sorted(trend_data.items(), key=lambda x: -sum(x[1]))[:10]

    for idx, (cat, vals) in enumerate(sorted_items):
        color = COLORS[idx % len(COLORS)]
        points = [f"{ts_to_x(i)},{val_to_y(v)}" for i, v in enumerate(vals[:num_ts])]
        if len(points) >= 2:
            poly = " ".join(points)
            lines.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2" opacity=".8"/>')
            # 终点圆点
            last_p = points[-1]
            x, y = last_p.split(",")
            lines.append(f'<circle cx="{x}" cy="{y}" r="3" fill="{color}"/>')
            # 最后值标签
            lines.append(f'<text x="{x}" y="{int(float(y))-6}" fill="{color}" font-size="8" text-anchor="middle">{vals[min(len(vals),num_ts)-1]}</text>')

    # X 轴时间标签（取等差分布的 5 个）
    for i in range(0, num_ts, max(1, num_ts // 5)):
        x = ts_to_x(i)
        label = timestamps[i] if i < len(timestamps) else ""
        lines.append(f'<text x="{x}" y="228" fill="#8b949e" font-size="8" text-anchor="middle" transform="rotate(-30,{x},228)">{escape(label)}</text>')

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="趋势与热力图报告")
    parser.add_argument("--kb", default=str(DEFAULT_KB))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--open", action="store_true", help="完成后在浏览器打开")
    args = parser.parse_args()

    kb = load_kb(Path(args.kb))
    html = generate_html(kb)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    history = kb.get("_meta", {}).get("run_history", [])
    print(f"[TREND] 报告已生成: {out_path}")
    print(f"        Bug 总量: {len(kb.get('bugs', {}))}")
    print(f"        历史轮次: {len(history)}")
    print(f"        分类数: {len(kb.get('_meta', {}).get('category_trend', {}))}")
    print(f"        文件: {len(html):,} bytes")

    if args.open:
        import webbrowser
        webbrowser.open(out_path.resolve().as_uri())


if __name__ == "__main__":
    main()
