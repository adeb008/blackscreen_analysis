"""经验库 Web 看板生成器"""
import psycopg2, json, os
from datetime import datetime

OUTPUT = r"D:\my_crew\outputs\dashboard\经验库看板.html"
DB_DSN = "host=localhost port=5433 dbname=blackscreen user=uidq2071 password=BlackScreen@2025"
SCHEMA = "8775_T1Q_国内"

def fetch(sql):
    conn = psycopg2.connect(DB_DSN, connect_timeout=5)
    cur = conn.cursor()
    cur.execute(sql)
    rows = cur.fetchall()
    cols = [desc[0] for desc in cur.description]
    conn.close()
    return rows_to_dicts(cols, rows)

def rows_to_dicts(cols, rows):
    import decimal
    result = []
    for r in rows:
        d = {}
        for c, v in zip(cols, r):
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v)
            elif isinstance(v, datetime):
                v = v.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(v, decimal.Decimal):
                v = float(v)
            elif v is None:
                v = ""
            d[c] = v
        result.append(d)
    return result

experiences   = fetch(f'SELECT * FROM "{SCHEMA}".experiences ORDER BY id')
design_lessons = fetch(f'SELECT * FROM "{SCHEMA}".design_lessons ORDER BY id')
category_stats = fetch(f'SELECT category, count(*) as cnt, round(avg(confidence)::numeric,2) as avg_conf FROM "{SCHEMA}".experiences GROUP BY category ORDER BY cnt DESC')
priority_stats = fetch(f'SELECT priority, count(*) FROM "{SCHEMA}".design_lessons GROUP BY priority ORDER BY count(*) DESC')

exp_time = max(r.get("updated_at") or r.get("created_at") or "" for r in experiences)
dl_time  = max(r.get("updated_at") or r.get("created_at") or "" for r in design_lessons)

summary = {
    "total": len(experiences) + len(design_lessons),
    "exp": len(experiences),
    "dl": len(design_lessons),
    "cats": len(category_stats),
    "p0": sum(1 for p in priority_stats if p["priority"] == "P0"),
    "updated": max(exp_time, dl_time),
}

# 注入数据作为 JS 变量
DATA_JS = f"""
const EXPERIENCES = {json.dumps(experiences, ensure_ascii=False)};
const DESIGN_LESSONS = {json.dumps(design_lessons, ensure_ascii=False)};
const CAT_STATS = {json.dumps(category_stats, ensure_ascii=False)};
const PRIO_STATS = {json.dumps(priority_stats, ensure_ascii=False)};
const SUMMARY = {json.dumps(summary, ensure_ascii=False)};
"""

print(f"数据：经验库{summary['exp']}条 + 设计经验{summary['dl']}条")

# ── HTML 模板 ──
HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>黑卡闪经验库看板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
:root { --bg:#0f1118; --card:#1a1d2e; --card-hover:#222640; --border:#2a2e45; --text:#e0e2f0; --text-dim:#8890b0; --accent:#5b7cfa; --accent-light:#7b9aff; --green:#4ade80; --red:#f87171; --orange:#fb923c; --gradient:linear-gradient(135deg,#5b7cfa,#a78bfa); }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif; background:var(--bg); color:var(--text); padding:24px; min-height:100vh; }
.header { display:flex; align-items:center; justify-content:space-between; margin-bottom:28px; }
.header h1 { font-size:24px; font-weight:700; background:var(--gradient); -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
.header .sub { color:var(--text-dim); font-size:14px; }
.cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:14px; margin-bottom:24px; }
.card { background:var(--card); border-radius:12px; padding:18px 20px; border:1px solid var(--border); transition:all .2s; }
.card:hover { background:var(--card-hover); border-color:var(--accent); }
.card .number { font-size:28px; font-weight:700; margin-bottom:4px; }
.card .label { font-size:13px; color:var(--text-dim); }
.chart-row { display:grid; grid-template-columns:1fr 1fr; gap:14px; margin-bottom:24px; }
.chart-box { background:var(--card); border-radius:12px; padding:20px; border:1px solid var(--border); height:280px; }
.chart-box h3 { font-size:15px; color:var(--text-dim); margin-bottom:12px; }
.chart-box canvas { max-height:220px; }
.tabs { display:flex; background:var(--card); border-radius:12px 12px 0 0; border:1px solid var(--border); border-bottom:none; overflow:hidden; }
.tab-btn { flex:1; padding:14px 20px; text-align:center; cursor:pointer; font-size:14px; font-weight:600; color:var(--text-dim); background:transparent; border:none; outline:none; transition:all .2s; position:relative; }
.tab-btn:hover { color:var(--text); background:rgba(91,124,250,.08); }
.tab-btn.active { color:var(--accent-light); background:rgba(91,124,250,.12); }
.tab-btn.active::after { content:''; position:absolute; bottom:0; left:20%; width:60%; height:2px; background:var(--accent); border-radius:2px; }
.tab-count { font-size:12px; background:rgba(91,124,250,.2); color:var(--accent-light); padding:1px 8px; border-radius:10px; margin-left:6px; }
.panel { background:var(--card); border-radius:0 0 12px 12px; border:1px solid var(--border); padding:16px; display:none; }
.panel.active { display:block; }
.toolbar { display:flex; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.search-input { flex:1; min-width:200px; padding:9px 14px; border-radius:8px; border:1px solid var(--border); background:var(--bg); color:var(--text); font-size:13px; outline:none; }
.search-input:focus { border-color:var(--accent); }
.filter-select { padding:9px 14px; border-radius:8px; border:1px solid var(--border); background:var(--bg); color:var(--text); font-size:13px; outline:none; cursor:pointer; min-width:120px; }
.table-wrap { overflow-x:auto; border-radius:8px; border:1px solid var(--border); }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; padding:10px 12px; background:rgba(255,255,255,.03); color:var(--text-dim); font-weight:600; cursor:pointer; white-space:nowrap; user-select:none; border-bottom:1px solid var(--border); }
th:hover { color:var(--accent-light); }
th .sort { margin-left:4px; opacity:.5; }
td { padding:10px 12px; border-bottom:1px solid rgba(42,46,69,.5); vertical-align:top; }
tr:hover td { background:rgba(91,124,250,.04); }
.expand-row { display:none; }
.expand-row td { padding:12px 16px 16px; background:rgba(0,0,0,.15); }
.expand-row.show { display:table-row; }
.detail-grid { display:grid; grid-template-columns:auto 1fr; gap:6px 14px; max-width:800px; font-size:13px; }
.detail-label { color:var(--text-dim); white-space:nowrap; }
.detail-value { color:var(--text); line-height:1.5; }
.tag { display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }
.tag-crash { background:rgba(248,113,113,.2); color:var(--red); }
.tag-qnx { background:rgba(96,165,250,.2); color:#60a5fa; }
.tag-hardware { background:rgba(251,146,60,.2); color:var(--orange); }
.tag-system { background:rgba(74,222,128,.2); color:var(--green); }
.tag-scene { background:rgba(251,191,36,.2); color:#fbbf24; }
.tag-env { background:rgba(167,139,250,.2); color:#a78bfa; }
.tag-app { background:rgba(91,219,222,.2); color:#5bdbde; }
.tag-p0 { background:rgba(248,113,113,.25); color:var(--red); }
.tag-p1 { background:rgba(251,146,60,.2); color:var(--orange); }
.tag-p2 { background:rgba(96,165,250,.2); color:#60a5fa; }
.empty { padding:40px; text-align:center; color:var(--text-dim); font-size:14px; }
.pagination { display:flex; justify-content:center; align-items:center; gap:8px; margin-top:14px; padding:8px 0; }
.page-btn { padding:6px 14px; border-radius:6px; border:1px solid var(--border); background:transparent; color:var(--text); cursor:pointer; font-size:13px; }
.page-btn:hover { background:var(--card-hover); border-color:var(--accent); }
.page-btn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
.page-btn:disabled { opacity:.3; cursor:default; }
.page-info { font-size:13px; color:var(--text-dim); margin:0 8px; }
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>&#x1F4CA; 黑卡闪经验库看板</h1>
    <div class="sub">8775_T1Q_国内 &middot; 最后更新 <span id="last-updated"></span></div>
  </div>
</div>
<div class="cards">
  <div class="card"><div class="number" id="stat-total" style="color:var(--accent-light)">-</div><div class="label">经验总计</div></div>
  <div class="card"><div class="number" id="stat-exp" style="color:#60a5fa">-</div><div class="label">经验库条目</div></div>
  <div class="card"><div class="number" id="stat-dl" style="color:#a78bfa">-</div><div class="label">设计经验</div></div>
  <div class="card"><div class="number" id="stat-cats" style="color:var(--green)">-</div><div class="label">分类数</div></div>
  <div class="card"><div class="number" id="stat-p0" style="color:var(--red)">-</div><div class="label">P0 优先级</div></div>
  <div class="card"><div class="number" id="stat-month" style="color:#fbbf24">-</div><div class="label">最近更新月份</div></div>
</div>
<div class="chart-row">
  <div class="chart-box"><h3>&#x1F4C8; 经验分类分布</h3><canvas id="catChart" height="200"></canvas></div>
  <div class="chart-box"><h3>&#x1F3AF; 设计经验优先级</h3><canvas id="prioChart" height="200"></canvas></div>
</div>
<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('experiences',this)">经验库 <span class="tab-count" id="tab-exp-count"></span></button>
  <button class="tab-btn" onclick="switchTab('design_lessons',this)">设计经验 <span class="tab-count" id="tab-dl-count"></span></button>
</div>

<!-- 经验库 -->
<div id="panel-experiences" class="panel active">
  <div class="toolbar">
    <input class="search-input" id="exp-search" placeholder="&#x1F50D; 搜索摘要、根因、解决方案..." oninput="renderExp()">
    <select class="filter-select" id="exp-cat-filter" onchange="renderExp()"><option value="">全部分类</option></select>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th onclick="sortExp('id')">ID <span class="sort">&#x2193;</span></th>
        <th onclick="sortExp('category')">分类 <span class="sort"></span></th>
        <th onclick="sortExp('subcategory')">子类 <span class="sort"></span></th>
        <th onclick="sortExp('summary')">摘要 <span class="sort"></span></th>
        <th onclick="sortExp('confidence')">置信度 <span class="sort"></span></th>
        <th onclick="sortExp('hit_count')">命中 <span class="sort"></span></th>
      </tr></thead>
      <tbody id="exp-tbody"></tbody>
    </table>
  </div>
  <div class="pagination" id="exp-page"></div>
</div>

<!-- 设计经验 -->
<div id="panel-design_lessons" class="panel">
  <div class="toolbar">
    <input class="search-input" id="dl-search" placeholder="&#x1F50D; 搜索标题、现象、根因..." oninput="renderDL()">
    <select class="filter-select" id="dl-prio-filter" onchange="renderDL()"><option value="">全部优先级</option></select>
  </div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th onclick="sortDL('id')">ID <span class="sort">&#x2193;</span></th>
        <th onclick="sortDL('lesson_title')">标题 <span class="sort"></span></th>
        <th onclick="sortDL('priority')">优先级 <span class="sort"></span></th>
        <th onclick="sortDL('arch_module')">模块 <span class="sort"></span></th>
        <th onclick="sortDL('phenomenon')">现象摘要 <span class="sort"></span></th>
      </tr></thead>
      <tbody id="dl-tbody"></tbody>
    </table>
  </div>
  <div class="pagination" id="dl-page"></div>
</div>

<script>
""" + DATA_JS + r"""
// ── 图表 ──
const CAT_COLORS = {'应用crash':'#f87171','QNX':'#60a5fa','硬件':'#fb923c','系统':'#4ade80','场景':'#fbbf24','环境':'#a78bfa','应用':'#5bdbde','需人工判断':'#f9a8d4'};
const PRIO_COLORS = {'P0':'#f87171','P1':'#fb923c','P2':'#60a5fa','P3':'#4ade80'};

// 摘要卡片
document.getElementById('stat-total').textContent = SUMMARY.total;
document.getElementById('stat-exp').textContent = SUMMARY.exp;
document.getElementById('stat-dl').textContent = SUMMARY.dl;
document.getElementById('stat-cats').textContent = SUMMARY.cats;
document.getElementById('stat-p0').textContent = SUMMARY.p0;
document.getElementById('stat-month').textContent = SUMMARY.updated.slice(0,7);
document.getElementById('last-updated').textContent = SUMMARY.updated;

new Chart(document.getElementById('catChart'), {
  type: 'bar',
  data: {
    labels: CAT_STATS.map(d => d.category.length > 10 ? d.category.slice(0,10)+'\u2026' : d.category),
    datasets: [{
      label: '条数', data: CAT_STATS.map(d => d.cnt),
      backgroundColor: CAT_STATS.map(d => CAT_COLORS[d.category.split('-')[0]] || '#5b7cfa'),
      borderRadius: 4,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      y: { beginAtZero: true, ticks: { stepSize: 1, color:'#8890b0' }, grid: { color:'rgba(42,46,69,.5)' } },
      x: { ticks: { color:'#8890b0', maxRotation: 45 } },
    }
  }
});

new Chart(document.getElementById('prioChart'), {
  type: 'doughnut',
  data: {
    labels: PRIO_STATS.map(d => d.priority),
    datasets: [{
      data: PRIO_STATS.map(d => d.count),
      backgroundColor: PRIO_STATS.map(d => PRIO_COLORS[d.priority] || '#5b7cfa'),
      borderWidth: 0,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { position: 'right', labels: { color:'#8890b0', padding:12 } } },
    cutout: '60%',
  }
});

// ── 表格 ──
const PAGE_SIZE = 15;
let expSort = {col:'id',dir:-1}, dlSort = {col:'id',dir:-1};
let expPage = 1, dlPage = 1;

function tagCat(category) {
  const m = {'应用crash':'crash','QNX':'qnx','硬件':'hardware','系统':'system','场景':'scene','环境':'env','应用':'app'};
  return 'tag-' + (m[category.split('-')[0]] || 'system');
}
function trunc(s,n) { if (!s) return '-'; n=n||60; return s.length>n?s.slice(0,n)+'\u2026':s; }
function escapeHtml(s) { if (!s) return ''; return String(s).replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function renderExp() {
  const q = document.getElementById('exp-search').value.toLowerCase();
  const cf = document.getElementById('exp-cat-filter').value;
  let data = EXPERIENCES.filter(d => {
    if (cf && d.category !== cf) return false;
    if (!q) return true;
    return (d.summary||'').toLowerCase().includes(q) || (d.root_cause||'').toLowerCase().includes(q)
        || (d.solution||'').toLowerCase().includes(q) || (d.keywords||'').toLowerCase().includes(q);
  });
  data.sort((a,b) => {
    let va = a[expSort.col], vb = b[expSort.col];
    if (expSort.col==='confidence'||expSort.col==='hit_count') {va=+va;vb=+vb;}
    return va>vb ? expSort.dir : va<vb ? -expSort.dir : 0;
  });
  const total = data.length, pages = Math.ceil(total/PAGE_SIZE)||1;
  expPage = Math.min(expPage, pages);
  const start = (expPage-1)*PAGE_SIZE, page = data.slice(start, start+PAGE_SIZE);
  document.getElementById('tab-exp-count').textContent = EXPERIENCES.length;
  
  let html = '';
  for (const d of page) {
    html += '<tr onclick="toggleExp('+d.id+')">'
      + '<td>'+d.id+'</td>'
      + '<td><span class="tag '+tagCat(d.category)+'">'+d.category+'</span></td>'
      + '<td>'+(d.subcategory||'-')+'</td>'
      + '<td>'+trunc(d.summary,50)+'</td>'
      + '<td>'+(d.confidence*100).toFixed(0)+'%</td>'
      + '<td>'+(d.hit_count||0)+'</td></tr>'
      + '<tr class="expand-row" id="exp-detail-'+d.id+'"><td colspan="6">'
      + '<div class="detail-grid">'
      + '<span class="detail-label">根因</span><span class="detail-value">'+escapeHtml(d.root_cause||'-')+'</span>'
      + '<span class="detail-label">解决</span><span class="detail-value">'+escapeHtml(d.solution||'-')+'</span>'
      + '<span class="detail-label">关键词</span><span class="detail-value">'+escapeHtml(d.keywords||'-')+'</span>'
      + '<span class="detail-label">来源</span><span class="detail-value">'+(d.source_bug||'-')+'</span>'
      + '</div></td></tr>';
  }
  if (!html) html = '<tr><td colspan="6"><div class="empty">无匹配记录</div></td></tr>';
  document.getElementById('exp-tbody').innerHTML = html;
  renderPage('exp-page', pages, expPage, (p) => { expPage=p; renderExp(); });
}

function toggleExp(id) {
  const row = document.getElementById('exp-detail-'+id);
  if (!row) return;
  document.querySelectorAll('.expand-row.show').forEach(r => r.classList.remove('show'));
  if (!row.classList.contains('show')) row.classList.add('show');
}
function sortExp(col) { expSort.dir = expSort.col===col ? -expSort.dir : -1; expSort.col=col; renderExp(); }

function renderDL() {
  const q = document.getElementById('dl-search').value.toLowerCase();
  const pf = document.getElementById('dl-prio-filter').value;
  let data = DESIGN_LESSONS.filter(d => {
    if (pf && d.priority !== pf) return false;
    if (!q) return true;
    return (d.lesson_title||'').toLowerCase().includes(q) || (d.phenomenon||'').toLowerCase().includes(q)
        || (d.root_cause||'').toLowerCase().includes(q);
  });
  data.sort((a,b) => {
    let va = a[dlSort.col], vb = b[dlSort.col];
    return va>vb ? dlSort.dir : va<vb ? -dlSort.dir : 0;
  });
  const total = data.length, pages = Math.ceil(total/PAGE_SIZE)||1;
  dlPage = Math.min(dlPage, pages);
  const start = (dlPage-1)*PAGE_SIZE, page = data.slice(start, start+PAGE_SIZE);
  document.getElementById('tab-dl-count').textContent = DESIGN_LESSONS.length;
  
  let html = '';
  for (const d of page) {
    html += '<tr onclick="toggleDL('+d.id+')">'
      + '<td>'+d.id+'</td>'
      + '<td>'+trunc(d.lesson_title,40)+'</td>'
      + '<td><span class="tag tag-'+d.priority.toLowerCase()+'">'+d.priority+'</span></td>'
      + '<td>'+(trunc(d.arch_module,35)||'-')+'</td>'
      + '<td>'+(trunc(d.phenomenon,50)||'-')+'</td></tr>'
      + '<tr class="expand-row" id="dl-detail-'+d.id+'"><td colspan="5">'
      + '<div class="detail-grid">'
      + '<span class="detail-label">根因</span><span class="detail-value">'+escapeHtml(d.root_cause||'-')+'</span>'
      + '<span class="detail-label">设计建议</span><span class="detail-value">'+escapeHtml(d.design_suggestion||'-')+'</span>'
      + '<span class="detail-label">模块</span><span class="detail-value">'+escapeHtml(d.arch_module||'-')+'</span>'
      + '<span class="detail-label">版本</span><span class="detail-value">'+(d.version||'-')+'</span>'
      + '<span class="detail-label">来源Bug</span><span class="detail-value">'+(d.source_bug_ids||'-')+'</span>'
      + '</div></td></tr>';
  }
  if (!html) html = '<tr><td colspan="5"><div class="empty">无匹配记录</div></td></tr>';
  document.getElementById('dl-tbody').innerHTML = html;
  renderPage('dl-page', pages, dlPage, (p) => { dlPage=p; renderDL(); });
}

function toggleDL(id) {
  const row = document.getElementById('dl-detail-'+id);
  if (!row) return;
  document.querySelectorAll('#panel-design_lessons .expand-row.show').forEach(r => r.classList.remove('show'));
  if (!row.classList.contains('show')) row.classList.add('show');
}
function sortDL(col) { dlSort.dir = dlSort.col===col ? -dlSort.dir : -1; dlSort.col=col; renderDL(); }

function renderPage(containerId, total, current, onClick) {
  let html = '<button class="page-btn" '+(current<=1?'disabled':'')+' onclick="onClick('+Math.max(1,current-1)+')">\u2039</button>'
    + '<span class="page-info">'+current+' / '+total+'</span>'
    + '<button class="page-btn" '+(current>=total?'disabled':'')+' onclick="onClick('+Math.min(total,current+1)+')">\u203a</button>';
  document.getElementById(containerId).innerHTML = html;
}

function switchTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('panel-'+tab).classList.add('active');
}

// ── 初始化 ──
(function() {
  const cats = [...new Set(EXPERIENCES.map(d => d.category))];
  const sel = document.getElementById('exp-cat-filter');
  cats.forEach(c => { const o=document.createElement('option'); o.value=c; o.textContent=c; sel.appendChild(o); });
  const prios = [...new Set(DESIGN_LESSONS.map(d => d.priority))];
  const sel2 = document.getElementById('dl-prio-filter');
  prios.forEach(p => { const o=document.createElement('option'); o.value=p; o.textContent=p; sel2.appendChild(o); });
  renderExp();
  renderDL();
})();
</script>
</body>
</html>"""

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(HTML)

print(f"✅ 看板生成完成：{OUTPUT}")
print(f"   文件大小：{os.path.getsize(OUTPUT)/1024:.0f} KB")
print(f"   双击 HTML 文件即可在浏览器打开")
