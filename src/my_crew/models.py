"""Pydantic 模型 + 25类分类规则唯一制源

FINE_GRAINED_RULES 是分类引擎的唯一事实来源。
CATEGORY_DEFINITIONS 从规则自动派生，供 Agent 参考。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

# ══════════════════════════════════════════════════════════════
# 25类细粒度根因分类规则（唯一制源）
# 权重: strong=3分, medium=2分, weak=1分
# 负向排除: exclude_keywords 命中则跳过该规则
# 优先级: 同分时 priority 高的胜出
# ══════════════════════════════════════════════════════════════

FINE_GRAINED_RULES: list[dict] = [

    # ── 应用层 Crash ──
    {
        "name": "应用crash-空指针/NPE",
        "description": "NullPointerException、空指针解引用、attempt to get length of null object",
        "keywords": {
            "strong": ["nullpointer", "空指针", "npe"],
            "medium": ["null object", "null array", "attempt to get length of null"],
            "weak": [],
        },
        "exclude_keywords": ["不是空指针", "排除npe", "非空指针"],
        "priority": 75,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "应用crash-ANR",
        "description": "应用无响应、Input dispatching timed out、Broadcast of intent timeout",
        "keywords": {
            "strong": ["anr", "应用无响应", "not responding"],
            "medium": ["input dispatching timed out", "broadcast of intent timed out"],
            "weak": ["无响应"],
        },
        "exclude_keywords": ["不是anr", "排除anr"],
        "priority": 75,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "应用crash-Native/SIG",
        "description": "SIGSEGV/SIGABRT/SIGBUS、tombstone、native crash、fatal signal",
        "keywords": {
            "strong": ["sigsegv", "sigabrt", "sigbus", "signal 11", "signal 6", "tombstone", "native crash"],
            "medium": ["fatal exception", "fatal signal", "backtrace", "signal 7", "nativecrash"],
            "weak": ["segv_maperr"],
        },
        "exclude_keywords": ["不是native", "不是crash"],
        "priority": 75,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "应用crash-Observer泄漏",
        "description": "ContentObserver 未反注册、重复注册、register/unregister 泄漏",
        "keywords": {
            "strong": ["observer", "未反注册", "没有反注册"],
            "medium": ["contentobserver", "重复注册", "反复注册", "unregister", "memory leak", "内存泄漏"],
            "weak": ["register"],
        },
        "exclude_keywords": ["不是observer", "排除observer"],
        "priority": 70,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "应用crash-跨进程/序列化",
        "description": "Binder/AIDL/IPC 通信异常、parcel 反序列化失败",
        "keywords": {
            "strong": ["binder", "跨进程", "aidl", "反序列化"],
            "medium": ["parcel", "序列化", "ipc"],
            "weak": [],
        },
        "exclude_keywords": [],
        "priority": 70,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "应用crash-三方应用",
        "description": "第三方应用异常（讯飞、雄狮、高德、Carota等）",
        "keywords": {
            "strong": ["com.lion.media", "carota", "讯飞", "雄狮"],
            "medium": ["外部问题", "第三方", "三方"],
            "weak": ["高德", "百度", "酷我", "第三方应用"],
        },
        "exclude_keywords": [],
        "priority": 65,
        "section": "一、已修复的问题及原因",
    },

    # ── QNX/底层 ──
    {
        "name": "QNX-SAIL/safetymonitor",
        "description": "SAIL 75ms 响应超时、safetymonitor 触发、功能安全事件、pshold 拉低",
        "keywords": {
            "strong": ["safetymonitor", "sail", "pshold", "功能安全"],
            "medium": ["75ms", "md response", "apss", "ramdump", "safety_mx", "safety monitor", "vsens"],
            "weak": [],
        },
        "exclude_keywords": ["不是sail", "排除sail", "非sail", "不是safety"],
        "priority": 85,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "QNX-IDPS/Kernel",
        "description": "IDPS crash、QNX kernel panic/shutdown、nidps 异常",
        "keywords": {
            "strong": ["idps", "nidps", "kernel panic", "kernel crash"],
            "medium": ["kernel shutdown", "qnx crash", "qnx kernel"],
            "weak": [],
        },
        "exclude_keywords": ["排除kernel"],
        "priority": 85,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "QNX-SPI/心跳/通信",
        "description": "SPI 通信中断、心跳丢失 0x80/0x5501、握手失败、io-sock/emac 驱动挂死",
        "keywords": {
            "strong": ["spi", "0x80", "0x5501", "io-sock", "emac", "驱动挂死", "5501"],
            "medium": ["心跳", "握手", "heartbeat", "保活"],
            "weak": ["通信链路", "通信异常"],
        },
        "exclude_keywords": ["不是spi", "排除spi", "非spi"],
        "priority": 80,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "QNX-启动/STR唤醒",
        "description": "STR 休眠唤醒异常、suspend/resume 失败、sr未 ready",
        "keywords": {
            "strong": ["str", "sr未ready", "sr ready"],
            "medium": ["休眠", "唤醒", "suspend", "resume", "sleep mode"],
            "weak": ["sleep", "wakeup"],
        },
        "exclude_keywords": [],
        "priority": 80,
        "section": "一、已修复的问题及原因",
    },

    # ── 硬件 ──
    {
        "name": "硬件-NOC/DDR/900E",
        "description": "NOC Error、DDR 错误、900E/9008 高通底层异常、NOR error",
        "keywords": {
            "strong": ["noc error", "900e", "9008", "nor error"],
            "medium": ["ddr", "0xac12e0", "qualcomm", "高通case"],
            "weak": ["硬件问题", "硬件故障"],
        },
        "exclude_keywords": ["不是硬件"],
        "priority": 90,
        "section": "二、未修复/挂起的问题",
    },
    {
        "name": "硬件-显示屏/解串器",
        "description": "解串器 SerDes 异常、DSI/LVDS link down、屏线束接触不良、显示屏显示异常",
        "keywords": {
            "strong": ["解串器", "serdes", "dsi", "lvds", "掉link", "link down"],
            "medium": ["显示屏", "屏线束", "寄存器", "mipi"],
            "weak": ["屏幕", "panel", "display"],
        },
        "exclude_keywords": [],
        "priority": 85,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "硬件-电源/供电",
        "description": "电源/供电异常、电流不足、电压波动、逆变器问题、5A/10A 限流",
        "keywords": {
            "strong": ["电源", "供电", "电压", "电流", "逆变器"],
            "medium": ["限流", "power supply", "供电不稳", "电源管理", "输入电源"],
            "weak": ["5a", "10a"],
        },
        "exclude_keywords": ["软件电源管理", "电源策略"],
        "priority": 85,
        "section": "一、已修复的问题及原因",
    },

    # ── 系统 ──
    {
        "name": "系统-升级/回滚/配置",
        "description": "OTA/FOTA 升级失败、版本回滚、标定文件配置错误、共板问题",
        "keywords": {
            "strong": ["升级失败", "回滚", "ota", "fota"],
            "medium": ["共板", "标定文件", "版本回退", "版本升级", "downgrade", "upgrade", "升级"],
            "weak": ["基线", "刷机"],
        },
        "exclude_keywords": ["不升级"],
        "priority": 70,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "系统-分区/存储损坏",
        "description": "userdata/metadata 分区损坏、断电导致分区乱码、文件系统 fsck",
        "keywords": {
            "strong": ["userdata", "metadata", "分区损坏", "分区乱码"],
            "medium": ["断电导致", "文件系统", "fsck", "数据损坏", "分区"],
            "weak": [],
        },
        "exclude_keywords": [],
        "priority": 70,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "系统-PAG/动画库",
        "description": "PAG/Lottie 动画渲染异常、GPU 渲染问题、OpenGL/Vulkan/Skia 异常",
        "keywords": {
            "strong": ["pag", "lottie", "gpu渲染"],
            "medium": ["动画库", "opengl", "vulkan", "skia"],
            "weak": ["动画", "特效", "渲染"],
        },
        "exclude_keywords": [],
        "priority": 65,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "系统-进程freeze/冻结",
        "description": "system_server 冻结、进程 freeze、冻屏卡死",
        "keywords": {
            "strong": ["freeze", "冻结", "冻屏", "进程冻结"],
            "medium": ["system_server", "process freeze", "程序被freeze"],
            "weak": ["卡死"],
        },
        "exclude_keywords": ["不卡死"],
        "priority": 70,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "系统-内存踩踏",
        "description": "踩内存/memory corruption、use-after-free、double free、野指针/kasan",
        "keywords": {
            "strong": ["踩内存", "memory corruption", "踩踏", "kasan", "use after free", "double free", "野指针"],
            "medium": ["内存越界", "wild pointer"],
            "weak": [],
        },
        "exclude_keywords": [],
        "priority": 75,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "系统-surface/fd泄漏",
        "description": "SurfaceFlinger FD 泄漏、too many open files、buffer/fence 泄漏",
        "keywords": {
            "strong": ["surfaceflinger", "fd泄漏", "too many open files"],
            "medium": ["文件描述符", "fence"],
            "weak": ["surface", "buffer"],
        },
        "exclude_keywords": [],
        "priority": 70,
        "section": "一、已修复的问题及原因",
    },

    # ── 环境 ──
    {
        "name": "环境-台架/线束/电源不稳",
        "description": "台架环境问题、线束接触不良、串口板影响、外部电源不稳",
        "keywords": {
            "strong": ["台架", "线束", "串口板", "座子浮高"],
            "medium": ["接触不良", "adb线", "拔掉线", "电源不稳", "电源波动", "外部电压"],
            "weak": [],
        },
        "exclude_keywords": [],
        "priority": 60,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "环境-测试手法/工具",
        "description": "测试操作不当（导U盘、dumpstate、monkey测试等）",
        "keywords": {
            "strong": ["dumpstate", "monkey", "mtbf", "regulartest"],
            "medium": ["导u盘", "log导出", "导日志", "slog2info"],
            "weak": ["测试指令", "测试脚本"],
        },
        "exclude_keywords": [],
        "priority": 55,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "环境-温度/高温",
        "description": "高温测试、散热问题、thermal 触发、85°C 环境",
        "keywords": {
            "strong": ["高温", "thermal", "85°"],
            "medium": ["温度", "水冷", "散热", "过热"],
            "weak": [],
        },
        "exclude_keywords": [],
        "priority": 55,
        "section": "一、已修复的问题及原因",
    },

    # ── 场景 ──
    {
        "name": "场景-CarPlay/Carlink",
        "description": "CarPlay/Carlink/HiCar 手机互联场景异常、CP 连接回连问题",
        "keywords": {
            "strong": ["carplay", "carlink", "hicar", "cp连接", "cp回连"],
            "medium": ["手机互联", "car life"],
            "weak": ["有线cp", "无线cp"],
        },
        "exclude_keywords": [],
        "priority": 50,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "场景-倒车/AVM",
        "description": "倒车/AVM/全景影像场景异常、R档切换问题",
        "keywords": {
            "strong": ["avm", "倒车", "r档", "倒挡", "rear view"],
            "medium": ["挂r", "全景", "摄像头"],
            "weak": ["camera"],
        },
        "exclude_keywords": [],
        "priority": 50,
        "section": "一、已修复的问题及原因",
    },
    {
        "name": "场景-USB/媒体",
        "description": "USB/U盘加载异常、音频/图库/媒体播放场景异常",
        "keywords": {
            "strong": ["u盘", "randomaccessfile", "图库"],
            "medium": ["歌曲", "音频", "音乐", "媒体", "usb加载", "usb"],
            "weak": ["图片"],
        },
        "exclude_keywords": [],
        "priority": 50,
        "section": "一、已修复的问题及原因",
    },
]

# 兜底分类
FALLBACK_CATEGORY = "需人工判断"
FALLBACK_SECTION = "三、核心问题分类统计"

# ══════════════════════════════════════════════════════════════
# 从 FINE_GRAINED_RULES 自动派生 CATEGORY_DEFINITIONS
#   → 供 LLM Agent 参考，不修改 FINE_GRAINED_RULES 源码
# ══════════════════════════════════════════════════════════════

CATEGORY_DEFINITIONS: list[dict] = [
    {
        "category": rule["name"],
        "description": rule.get("description", rule["name"]),
    }
    for rule in FINE_GRAINED_RULES
]
CATEGORY_DEFINITIONS.append({
    "category": FALLBACK_CATEGORY,
    "description": "不属于以上任何已知类别，需要人工判断",
})

# ══════════════════════════════════════════════════════════════
# 自动合并 LLM 自学习关键词（不修改 FINE_GRAINED_RULES 源码）
#   keywords_override.json 由 scripts/learn_keywords_from_llm.py 生成
#   将学习到的关键词作为 weak 级别（权重 1）合并到规则中
# ══════════════════════════════════════════════════════════════

_OVERRIDE_PATH = (Path(__file__).resolve().parent.parent.parent /
                  "outputs" / "keywords_override.json")

if _OVERRIDE_PATH.exists():
    try:
        import json as _json
        _overrides = _json.loads(_OVERRIDE_PATH.read_text(encoding="utf-8"))
        _rule_map = {r["name"]: r for r in FINE_GRAINED_RULES}
        _added = 0
        for _cat, _kws in _overrides.items():
            if _cat in _rule_map:
                _rule = _rule_map[_cat]
                _weak_set = set(k.lower() for k in _rule["keywords"].get("weak", []))
                for _kw in _kws:
                    if _kw.lower() not in _weak_set:
                        _rule["keywords"].setdefault("weak", []).append(_kw)
                        _weak_set.add(_kw.lower())
                        _added += 1
            else:
                # 如果分类名不在规则中，忽略（可能是 LLM 误编的分类）
                pass
        if _added > 0:
            print(f"[models] 已合并 {_added} 个自学习关键词到分类规则")
    except Exception as _e:
        print(f"[models] 加载关键词覆盖失败: {_e}")


# ══════════════════════════════════════════════════════════════
# Pydantic 模型（方案B 结构化输出参考，DeepSeek 不直接使用）
# ══════════════════════════════════════════════════════════════

class BugClassification(BaseModel):
    """单条 Bug 的精校分类结果"""
    bug_id: str = Field(description="Bug ID，如 BUG20260421_12537")
    title: str = Field(description="Bug 标题")
    original_category: str = Field(description="工具自动分类的原分类")
    refined_category: str = Field(description="LLM 二次精校后的分类，必须从 25 类中选取")
    confidence: str = Field(description="精校置信度：高/中/低")
    change_reason: Optional[str] = Field(
        default=None,
        description="如果分类改变了，说明为什么改",
    )
    key_evidence: str = Field(description="判断依据：从 Bug 描述中提取的关键证据原文片段")


class RefinedClassifications(BaseModel):
    """方案B 输出模型：issue_refiner 对 data_analyst 的分类结果做二次精校"""
    report_chapter_one: str = Field(
        description="第一章：已修复的问题及原因（按根因大类分组的Markdown表格）"
    )
    report_chapter_two: str = Field(
        description="第二章：未修复/挂起的问题（Markdown表格）"
    )
    report_chapter_three: str = Field(
        description="第三章：核心问题分类统计（含占比和处理状态的Markdown表格）"
    )
    refined_classifications: list[BugClassification] = Field(
        description="每条 Bug 的二次精校分类结果清单"
    )
    corrections_summary: str = Field(
        description="精校概览：纠正了多少条、主要修正了哪些分类、发现了什么模式"
    )


# ══════════════════════════════════════════════════════════════
# 辅助
# ══════════════════════════════════════════════════════════════

def get_category_names() -> list[str]:
    """返回 25 类名称列表"""
    return [rule["name"] for rule in FINE_GRAINED_RULES] + [FALLBACK_CATEGORY]


def get_category_description(name: str) -> str:
    """按名称查找分类描述"""
    for rule in FINE_GRAINED_RULES:
        if rule["name"] == name:
            return rule.get("description", name)
    if name == FALLBACK_CATEGORY:
        return "不属于以上任何已知类别"
    return name
