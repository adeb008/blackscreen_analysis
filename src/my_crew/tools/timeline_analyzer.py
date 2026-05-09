"""多源日志时间线分析器 — 整合 MCU/QNX/Android 日志，还原问题全貌"""

from __future__ import annotations

import gzip
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# ── MCU SPI 原因码映射 ──
REASON_MAP = {
    "00": "MCU_RESET_DEFAULT",
    "01": "MCU_NMI_INTERRUPT",
    "02": "MCU_HARDFAULT_INTERRUPT",
    "03": "MCU_MEMMANAGE_INTERRUPT",
    "04": "MCU_BUSFAULT_INTERRUPT",
    "05": "MCU_USAGEFAULT_INTERRUPT",
    "06": "MCU_RST_STR_PONR",
    "07": "MCU_RST_STR_INITX",
    "08": "MCU_RST_STR_SWDG",
    "09": "MCU_RST_STR_HWDG",
    "0A": "MCU_RST_STR_CSVR",
    "0B": "MCU_RST_STR_FCSR",
    "0C": "MCU_RST_STR_SRST",
    "10": "NAVI_RESET_SPECIAL_RESET_TEST_EVENT",
    "11": "NAVI_RESET_ENGINEER_INIT",
    "12": "NAVI_RESET_SWDL_RADIO",
    "13": "NAVI_RESET_REQ_RESET_EVENT",
    "14": "NAVI_RESET_ENGINEER_FACTORY_INIT",
    "15": "NAVI_RESET_MAP_UPGRADE",
    "1B": "NAVI_RESET_SOC_RUN_ERROR",
    "1C": "NAVI_RESET_SOC_SLEEP_FAIL",
    "1D": "NAVI_RESET_AMP_ERROR",
    "1E": "NAVI_RESET_REQ_OTA_EVENT",
    "20": "NAVI_RESET_AIC3254_ERROR_DETECT",
    "22": "NAVI_RESET_DIAG_HARDKEY_FORCE_RESET",
    "27": "NAVI_1HZ_SIGNAL_20S_TIMEOUT",
    "2C": "NAVI_RESET_BY_ONSELF (SPI 2次握手→900E)",
    "2D": "NAVI_RESET_SPI_OVER_TIME_ERROR",
    "2E": "NAVI_RESET_WAIT_SOC_RESPONSE_ERROR",
    "2F": "NAVI_RESET_SPI_RESEND_TIMEOUT_ERROR",
    "33": "NAVI_RESET_ACC_ON_IRQ",
    "34": "NAVI_RESET_RVC_ON_IRQ",
    "35": "NAVI_RESET_CAN_IRQ",
    "3E": "NAVI_RESET_SOC_WAKE_IRQ",
    "3F": "MCU_RESET_SECURITY_BOOT_FAIL",
    "60": "NAVI_SOC_REQ_RESET_QNX",
    "61": "NAVI_SOC_REQ_RESET_SCREEN_ABNORMAL",
    "63": "NAVI_SOC_REQ_RESET_EMMC_ABNORMAL",
    "A0": "MCU_REQ_RESET_QNX_FIRST_CONNECT_TIMEROUT",
    "A2": "MCU_REQ_RESET_UART_HANDSHAKE_TIMEOUT_ERROR",
    "A7": "MCU_REQ_RESET_TEMPERATURE_ABNORMAL",
    "AA": "MCU_REQ_RESET_ENTER_TO_STR_FAIL_TIMEROUT",
    "AB": "MCU_REQ_RESET_EXIT_TO_STR_FAIL_TIMEROUT",
    "AC": "MCU_REQ_RESET_ANDROID_HEARTBEAT_CONNECT_TIMEROUT",
    "AE": "MCU_REQ_RESET_STR_INTERRUPTED",
    "B3": "MCU_REQ_RESET_LINUX_MP_HEART_LOSS",
    "B4": "MCU_REQ_RESET_MP_LINUX_HEART_LOSS",
    "B5": "MCU_REQ_RESET_STR_SOC_WAKEUP_TIMING_REBOOT",
    "CA": "MCU_REQ_RESET_SAFE_RESET",
    "CB": "MCU_REQ_RESET_SAFE_MPU_RESET",
}
# 黑屏高关联码
BLACKSCREEN_CODES = {"1B", "1C", "27", "2C", "2D", "2E", "2F", "A0", "A2", "A7",
                     "AA", "AB", "AC", "AE", "B3", "B4", "CA", "CB"}

# ── 日志解析 ──

def parse_mcu_spi_events(log_dir: Path) -> list[dict]:
    """解析 vehicle_spi_log 中的 MCU 重启事件"""
    events = []
    spi_dir = log_dir / "vehicle_spi_log"
    if not spi_dir.exists():
        spi_dir = log_dir / "spi_decode"
    if not spi_dir.exists():
        # Search recursively
        for d in log_dir.rglob("vehicle_spi_log"):
            spi_dir = d
            break

    if not spi_dir.exists():
        return events

    # Decompress .gz files first
    decoded_dir = spi_dir.parent / "spi_decoded"
    decoded_dir.mkdir(exist_ok=True)
    for f in spi_dir.rglob("*"):
        if f.suffix == ".gz":
            out = decoded_dir / f.stem
            if not out.exists():
                try:
                    with gzip.open(f, "rb") as fin, open(out, "wb") as fout:
                        fout.write(fin.read())
                except Exception:
                    pass
        elif f.name == "vehicle_spi.log" or f.name.startswith("vehicle_spi.log"):
            out = decoded_dir / f.name
            if not out.exists():
                try:
                    out.write_bytes(f.read_bytes())
                except Exception:
                    pass

    # Parse decoded files
    all_files = sorted(decoded_dir.glob("vehicle_spi.log*"),
                       key=lambda x: (0, 0) if x.name == "vehicle_spi.log"
                       else (1, int(x.suffix.lstrip(".")) if x.suffix.lstrip(".").isdigit() else 999))

    pattern = re.compile(
        r"0179300900([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})"
        r"([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})"
        r"([0-9A-Fa-f]{2})([0-9A-Fa-f]{2})"
    )
    seen = set()

    for f in all_files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            for line in text.split("\n"):
                clean = line.strip().replace(" ", "").upper()
                if "0179300900" not in clean:
                    continue
                m = pattern.search(clean)
                if not m:
                    continue

                id_hex = m.group(1)
                flag_hex = m.group(2)
                reason_hex = m.group(3).upper()
                year = int(m.group(4), 16) + 2000
                month = int(m.group(5), 16)
                day = int(m.group(6), 16)
                hour = int(m.group(7), 16)
                minute = int(m.group(8), 16)

                ts = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"
                key = (id_hex, flag_hex, reason_hex, ts)
                if key in seen:
                    continue
                seen.add(key)

                reason = REASON_MAP.get(reason_hex, f"未知_{reason_hex}")
                is_black = reason_hex in BLACKSCREEN_CODES
                events.append({
                    "timestamp": ts,
                    "layer": "MCU",
                    "type": "SPI Restart",
                    "reason_code": reason_hex,
                    "reason": reason,
                    "flag": flag_hex,
                    "is_blackscreen": is_black,
                    "source": f.name,
                    "severity": "critical" if is_black else "info",
                })
        except Exception:
            pass

    return sorted(events, key=lambda e: e["timestamp"])


def parse_qnx_events(log_dir: Path) -> list[dict]:
    """从 QNX 日志提取关键事件"""
    events = []
    qnx_dir = None
    for d in log_dir.rglob("qnx"):
        if d.is_dir():
            qnx_dir = d
            break

    if not qnx_dir:
        return events

    # Key patterns to look for
    patterns = [
        (r"SAIL.*timeout|safetymonitor.*75ms|safety_monitor", "SAIL/safetymonitor", "critical"),
        (r"kernel crash|kernel panic|kernel shutdown", "Kernel Crash", "critical"),
        (r"NOC error|DDR.*error|900E", "NOC/DDR Error", "critical"),
        (r"emac.*error|io-sock.*error|emac.*timeout", "EMAC/IOSock Error", "critical"),
        (r"SPI.*heartbeat|5501.*80|0x80.*0x5501", "SPI Heartbeat", "warning"),
        (r"STR.*enter|STR.*exit|sleep.*mode|suspend|resume", "STR Event", "info"),
        (r"pshold.*low|PS_HOLD|PMA_GPIO_2.*low", "PSHold/PMU Event", "critical"),
        (r"ramdump|RAMDUMP", "RAMDUMP", "critical"),
        (r"qcore.*abnormal|qcore.*crash", "QCore Crash", "critical"),
        (r"serializer|deserializer|串化器|解串器", "SerDes Error", "warning"),
    ]

    for f in qnx_dir.rglob("*"):
        if not f.is_file() or f.suffix == ".gz":
            continue
        try:
            # Try to read as text, skip binary
            text = f.read_text(encoding="utf-8", errors="ignore")[:500000]
            for line in text.split("\n"):
                # Extract timestamp
                ts_match = re.search(
                    r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
                if not ts_match:
                    ts_match = re.search(
                        r"\[(\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]", line)
                    if ts_match:
                        ts_str = ts_match.group(1)
                        ts = f"20{ts_str[:2]}-{ts_str[3:5]}-{ts_str[6:8]} {ts_str[9:]}"
                    else:
                        continue
                else:
                    ts = ts_match.group(1).replace("/", "-")

                for pattern, event_type, severity in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        events.append({
                            "timestamp": ts,
                            "layer": "QNX",
                            "type": event_type,
                            "detail": line.strip()[:200],
                            "severity": severity,
                            "source": f.name,
                        })
                        break
        except Exception:
            pass

    return sorted(events, key=lambda e: e["timestamp"])


def parse_android_events(log_dir: Path) -> list[dict]:
    """从 Android 日志提取关键事件"""
    events = []

    # ANR traces
    anr_dir = None
    for d in log_dir.rglob("anr"):
        if d.is_dir():
            anr_dir = d
            break
    if anr_dir:
        for f in anr_dir.rglob("*"):
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")[:100000]
                    for line in text.split("\n"):
                        ts_match = re.search(
                            r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})", line)
                        if not ts_match:
                            continue
                        if "ANR" in line or "Input dispatching timed out" in line:
                            events.append({
                                "timestamp": ts_match.group(1).replace("/", "-"),
                                "layer": "Android",
                                "type": "ANR",
                                "detail": line.strip()[:200],
                                "severity": "warning",
                                "source": f.name,
                            })
                except Exception:
                    pass

    # Tombstones
    tomb_dir = None
    for d in log_dir.rglob("tombstones"):
        if d.is_dir():
            tomb_dir = d
            break
    if tomb_dir:
        for f in tomb_dir.rglob("*"):
            if f.is_file():
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")[:100000]
                    for line in text.split("\n"):
                        if "signal" in line.lower() and "SIG" in line:
                            ts_match = re.search(
                                r"(\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2})", line)
                            ts = ts_match.group(1).replace("/", "-") if ts_match else ""
                            events.append({
                                "timestamp": ts or "unknown",
                                "layer": "Android",
                                "type": "Native Crash",
                                "detail": line.strip()[:200],
                                "severity": "critical",
                                "source": f.name,
                            })
                except Exception:
                    pass

    # Logcat FATAL
    logcat_dir = None
    for d in log_dir.rglob("logcat"):
        if d.is_dir():
            logcat_dir = d
            break
    if logcat_dir:
        for f in logcat_dir.rglob("*"):
            if not f.is_file() or f.suffix == ".gz":
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")[:500000]
                for line in text.split("\n"):
                    if "FATAL EXCEPTION" in line or "AndroidRuntime" in line:
                        ts_match = re.search(
                            r"(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)", line)
                        if ts_match:
                            ts_str = ts_match.group(1)
                            ts = f"2025-{ts_str}"
                        else:
                            ts = ""
                        events.append({
                            "timestamp": ts,
                            "layer": "Android",
                            "type": "FATAL Crash",
                            "detail": line.strip()[:200],
                            "severity": "critical",
                            "source": f.name,
                        })
            except Exception:
                pass

    return sorted(events, key=lambda e: e["timestamp"])


# ── 时间线构建 ──

def build_timeline(log_dir: str | Path, problem_time: str = "",
                   bug_id: str = "", title: str = "") -> dict:
    """构建完整时间线"""
    log_dir = Path(log_dir)

    mcu_events = parse_mcu_spi_events(log_dir)
    qnx_events = parse_qnx_events(log_dir)
    android_events = parse_android_events(log_dir)

    all_events = mcu_events + qnx_events + android_events
    all_events.sort(key=lambda e: e["timestamp"])

    # 确定时间范围
    timestamps = [e["timestamp"] for e in all_events if e["timestamp"] and e["timestamp"] != "unknown"]
    time_range = {"start": timestamps[0] if timestamps else "N/A",
                  "end": timestamps[-1] if timestamps else "N/A"}

    # 聚焦问题时间窗口
    focus_events = []
    if problem_time:
        try:
            pt = datetime.strptime(problem_time[:16], "%Y-%m-%d %H:%M")
            window_start = (pt - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M")
            window_end = (pt + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M")
            for e in all_events:
                if window_start <= e.get("timestamp", "") <= window_end:
                    focus_events.append(e)
        except ValueError:
            focus_events = all_events
    else:
        focus_events = all_events

    # 统计
    stats = {
        "total_events": len(all_events),
        "mcu_events": len(mcu_events),
        "qnx_events": len(qnx_events),
        "android_events": len(android_events),
        "blackscreen_spi": sum(1 for e in mcu_events if e.get("is_blackscreen")),
        "critical_events": sum(1 for e in all_events if e.get("severity") == "critical"),
        "focus_window_count": len(focus_events),
    }

    return {
        "bug_id": bug_id,
        "title": title,
        "problem_time": problem_time,
        "time_range": time_range,
        "stats": stats,
        "mcu_events": mcu_events,
        "qnx_events": qnx_events,
        "android_events": android_events,
        "all_events": all_events,
        "focus_events": focus_events,
    }


# ── HTML 时间线渲染 ──

def render_timeline_html(timeline: dict, output_path: str | Path) -> str:
    """生成 HTML 时间线视图"""
    all_events = timeline["focus_events"] or timeline["all_events"]
    stats = timeline["stats"]
    time_range = timeline["time_range"]

    severity_colors = {
        "critical": "#f85149",
        "warning": "#d2991d",
        "info": "#58a6ff",
    }
    layer_icons = {"MCU": "🔌", "QNX": "💻", "Android": "📱"}

    # Group events by time (1-min buckets)
    time_buckets = defaultdict(list)
    for e in all_events:
        ts = e.get("timestamp", "unknown")
        if ts != "unknown" and len(ts) >= 16:
            bucket = ts[:16]  # YYYY-MM-DD HH:MM
        else:
            bucket = "unknown"
        time_buckets[bucket].append(e)

    # Build event rows
    event_rows = ""
    for bucket in sorted(time_buckets.keys()):
        events = time_buckets[bucket]
        for e in events:
            icon = layer_icons.get(e.get("layer", ""), "")
            color = severity_colors.get(e.get("severity", "info"), "#8b949e")
            detail = e.get("detail", "") or e.get("reason", "")
            if len(detail) > 120:
                detail = detail[:117] + "..."

            is_bs = "bs-event" if e.get("is_blackscreen") else ""

            event_rows += f"""
            <tr class="event-row {is_bs}" data-layer="{e.get('layer', '')}">
                <td class="ts">{e.get('timestamp', '')}</td>
                <td class="layer-icon">{icon}</td>
                <td class="layer-label">{e.get('layer', '')}</td>
                <td class="type-label" style="color:{color}">{e.get('type', '')}</td>
                <td class="detail">{detail}</td>
                <td class="src">{e.get('source', '')}</td>
            </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>黑卡闪日志时间线 - {timeline.get('bug_id', '')}</title>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --accent: #58a6ff; --green: #3fb950;
    --orange: #d2991d; --red: #f85149;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: 'Consolas', 'Microsoft YaHei', monospace;
    padding: 20px;
  }}
  .container {{ max-width: 1400px; margin: 0 auto; }}
  .header {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; margin-bottom: 20px;
  }}
  .header h1 {{ font-size: 22px; color: var(--accent); margin-bottom: 8px; }}
  .header .meta {{ color: #8b949e; font-size: 13px; }}
  .stats {{
    display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px;
  }}
  .stat {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 6px; padding: 12px 16px; text-align: center; min-width: 100px;
  }}
  .stat .num {{ font-size: 24px; font-weight: 700; }}
  .stat .label {{ font-size: 11px; color: #8b949e; margin-top: 2px; }}
  .filters {{
    display: flex; gap: 10px; margin-bottom: 16px; flex-wrap: wrap;
  }}
  .filters button {{
    background: var(--card); border: 1px solid var(--border);
    color: var(--text); padding: 6px 14px; border-radius: 4px;
    cursor: pointer; font-size: 13px;
  }}
  .filters button.active {{ background: #1f6feb; border-color: #1f6feb; }}
  .filters button:hover {{ border-color: var(--accent); }}
  table {{
    width: 100%; border-collapse: collapse;
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; overflow: hidden;
  }}
  th {{
    background: #21262d; padding: 10px 12px;
    text-align: left; font-size: 12px; color: #8b949e;
    border-bottom: 1px solid var(--border); position: sticky; top: 0; z-index: 1;
  }}
  td {{ padding: 8px 12px; font-size: 13px; border-bottom: 1px solid var(--border); }}
  .event-row:hover {{ background: #1a2332; }}
  .bs-event {{ border-left: 3px solid var(--red); }}
  .ts {{ color: var(--accent); white-space: nowrap; font-size: 12px; }}
  .layer-icon {{ width: 24px; text-align: center; }}
  .layer-label {{ font-weight: 600; font-size: 11px; color: #8b949e; }}
  .type-label {{ font-weight: 600; }}
  .detail {{ max-width: 500px; word-break: break-all; }}
  .src {{ font-size: 11px; color: #484f58; max-width: 150px; word-break: break-all; }}
  .timeline-summary {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px; margin-top: 20px;
    font-size: 13px; line-height: 1.8;
  }}
  .timeline-summary h3 {{ color: var(--accent); margin-bottom: 8px; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>黑卡闪日志时间线分析</h1>
    <div class="meta">
      Bug ID: <strong>{timeline.get('bug_id', 'N/A')}</strong> |
      标题: {timeline.get('title', 'N/A')[:80]} |
      问题时间: <strong>{timeline.get('problem_time', 'N/A')}</strong>
    </div>
    <div class="meta" style="margin-top:4px">
      时间范围: {time_range.get('start', 'N/A')} ~ {time_range.get('end', 'N/A')} |
      聚焦窗口: 问题时间前10分钟 ~ 后5分钟
    </div>
  </div>

  <div class="stats">
    <div class="stat">
      <div class="num" style="color:var(--accent)">{stats.get('total_events', 0)}</div>
      <div class="label">总事件</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--orange)">{stats.get('mcu_events', 0)}</div>
      <div class="label">MCU SPI</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--accent)">{stats.get('qnx_events', 0)}</div>
      <div class="label">QNX</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--green)">{stats.get('android_events', 0)}</div>
      <div class="label">Android</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--red)">{stats.get('blackscreen_spi', 0)}</div>
      <div class="label">黑屏SPI事件</div>
    </div>
    <div class="stat">
      <div class="num" style="color:var(--red)">{stats.get('critical_events', 0)}</div>
      <div class="label">严重事件</div>
    </div>
  </div>

  <div class="filters">
    <button class="active" onclick="filterLayer('all')">全部 ({stats.get('focus_window_count', stats.get('total_events', 0))})</button>
    <button onclick="filterLayer('MCU')">MCU ({stats.get('mcu_events', 0)})</button>
    <button onclick="filterLayer('QNX')">QNX ({stats.get('qnx_events', 0)})</button>
    <button onclick="filterLayer('Android')">Android ({stats.get('android_events', 0)})</button>
    <button onclick="filterLayer('critical')" style="color:var(--red)">仅严重 ({stats.get('critical_events', 0)})</button>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:140px">时间</th>
        <th style="width:30px"></th>
        <th style="width:60px">层</th>
        <th style="width:180px">事件类型</th>
        <th>详情</th>
        <th style="width:120px">来源</th>
      </tr>
    </thead>
    <tbody>
      {event_rows}
    </tbody>
  </table>

  <div class="timeline-summary">
    <h3>自动摘要</h3>
    <p>📊 在 {time_range.get('start', 'N/A')} ~ {time_range.get('end', 'N/A')} 期间，共捕获 <strong>{stats.get('total_events', 0)}</strong> 条事件。</p>
    <p>🔴 其中 <strong>{stats.get('critical_events', 0)}</strong> 条为严重事件，<strong>{stats.get('blackscreen_spi', 0)}</strong> 条 SPI 事件与黑屏高度相关。</p>
    <p>📍 日志覆盖率: MCU={stats.get('mcu_events', 0)} | QNX={stats.get('qnx_events', 0)} | Android={stats.get('android_events', 0)}</p>
  </div>
</div>

<script>
function filterLayer(layer) {{
  document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('.event-row').forEach(row => {{
    if (layer === 'all') {{
      row.style.display = '';
    }} else if (layer === 'critical') {{
      row.style.display = row.querySelector('.type-label').style.color === 'rgb(248, 81, 73)' ? '' : 'none';
    }} else {{
      row.style.display = row.dataset.layer === layer ? '' : 'none';
    }}
  }});
}}
</script>
</body>
</html>"""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    return str(output)


# ── CLI ──
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python timeline_analyzer.py <log_dir> [problem_time] [bug_id]")
        sys.exit(1)

    log_dir = sys.argv[1]
    problem_time = sys.argv[2] if len(sys.argv) > 2 else ""
    bug_id = sys.argv[3] if len(sys.argv) > 3 else ""

    timeline = build_timeline(log_dir, problem_time, bug_id)
    out = f"reports/timeline_{bug_id or 'analysis'}.html"
    path = render_timeline_html(timeline, out)
    print(f"Timeline generated: {path}")
    print(f"Total events: {timeline['stats']['total_events']}")
    print(f"MCU: {timeline['stats']['mcu_events']} | QNX: {timeline['stats']['qnx_events']} | Android: {timeline['stats']['android_events']}")
