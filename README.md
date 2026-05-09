# 黑卡闪问题提炼分析 CrewAI 工作流

基于《黑卡闪问题提炼分析》的标准报告格式，实现从 Bug Excel 到结构化分析报告的自动流水线。

## 工作流

```
Bug Excel (.xlsx)
       │
       ▼
┌──────────────────────────────────────────────────────┐
│  Agent 1: 数据工程师 (data_analyst)                    │
│  └─ 工具: ExcelIssueAnalyzer                          │
│  └─ 输出: 结构化摘要 (字段映射/分布/根因分类/交叉统计)    │
│                                                        │
│  Agent 2: 提炼专家 (issue_refiner)                     │
│  └─ 输出: 报告前三章                                   │
│     ├── 一、已修复的问题及原因 (按8个根因大类分组)        │
│     ├── 二、未修复/挂起的问题 (卡点分析)                 │
│     └── 三、核心问题分类统计 (分布+占比)                │
│                                                        │
│  Agent 3: 报告撰写员 (report_writer)                   │
│  └─ 输出: 完整五段式报告                               │
│     ├── 四、需要提炼的经验点 (P0-P4层级+10条经验模式)    │
│     └── 五、总结 (收敛/风险/建议)                      │
└──────────────────────────────────────────────────────┘
       │
       ▼
outputs/report.md  ← 标准格式《黑卡闪问题提炼分析报告》
```

## 使用方法

```bash
# 安装依赖
pip install crewai openpyxl

# 运行（默认使用 black_screen_data/ 下的测试数据）
crewai run

# 指定自定义 Excel 路径
python -m my_crew.main "D:/bugs/黑卡闪Bug清单.xlsx"
```

## 根因分类体系（11类）

工具自动按关键词匹配归类：

| 根因大类 | 归属章节 | 关键词示例 |
|---------|---------|-----------|
| SAIL/safetymonitor 异常类 | 已修复 | safetymonitor, SAIL, 75ms, ramdump |
| IDPS / QNX Kernel Crash | 已修复 | idps, nidps, kernel crash |
| 心跳/握手/通信异常 | 已修复 | SPI, 握手, 0x80, 心跳 |
| 内存问题类 | 已修复 | 内存, memory, kasan |
| Android 应用层问题 | 已修复 | surfaceflinger, ANR, watchdog |
| 电源/供电问题 | 已修复 | 电源, 供电, 电流 |
| 软件配置/升级问题 | 已修复 | 升级, 回滚, 共板 |
| NOC Error/DDR/900E | 未修复 | NOC error, DDR, 900E |
| io-sock/emac 驱动 | 未修复 | io-sock, emac |
| 测试手法/环境问题 | 已修复 | 台架, 高温, 水冷 |
| 无法复现/日志不全 | 统计 | 无法复现, 日志不全 |

## 输出报告结构

```markdown
# 黑卡闪问题提炼分析

## 一、已修复的问题及原因
### 1. SAIL/safetymonitor 异常类
| Bug ID | 问题现象 | 根因 | 修复方式 |
### 2. IDPS / QNX Kernel Crash 类
...

## 二、未修复/挂起的问题
| Bug ID | 状态 | 问题现象 | 当前卡点 |

## 三、核心问题分类统计
| 根因大类 | 数量 | 占比 | 处理状态 |

## 四、需要提炼的经验点
### 经验1：xxx
- **现象：**
- **痛点：**
- **建议：**

## 五、总结
| 维度 | 结论 |

## 项目结构

```
my_crew/
├── src/my_crew/
│   ├── crew.py              # Crew 编排（3 agents × 3 tasks）
│   ├── main.py              # CLI 入口
│   ├── config/
│   │   ├── agents.yaml      # Agent 角色定义
│   │   └── tasks.yaml       # Task 描述和输出格式
│   └── tools/
│       └── excel_issue_tool.py  # Excel 读取 + 根因分类
├── black_screen_data/       # 测试数据
├── outputs/
│   └── report.md            # 输出报告
└── pyproject.toml
```
