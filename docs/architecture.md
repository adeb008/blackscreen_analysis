# 黑卡闪问题自动化分析工作流 —— 需求与架构设计

> 版本: v1.1 | 日期: 2026-05-09 | 状态: 设计评审
> 项目: D:\my_crew | 框架: CrewAI
> 数据源: 本地 Excel 导出（`black_screen_data/Bug_*.xlsx`）

---

## 目录

1. [需求分析](#一需求分析)
2. [软件架构设计](#二软件架构设计)
3. [接口设计](#三接口设计)
4. [日志分析流程设计](#四日志分析流程设计)
5. [CrewAI Agent/Task 设计](#五crewai-agenttask-设计)
6. [实施路线图](#六实施路线图)

---

## 一、需求分析

### 1.1 业务背景

黑卡闪（Black Screen Flash）是车载座舱系统中最严重的用户体验问题之一。当前的分析流程完全依赖人工：
- 测试人员在 Trinity 系统提交 bug
- 分析人员手动搜索 Analysis 状态的 bug
- 从 Actual Result 中提取日志路径，手动下载
- 逐层分析 MCU → QNX → Android 日志
- 编写分析报告发给开发确认

**痛点：** 449 条历史问题中，31.4% 信息缺失、40.5% 方案未记录，知识沉淀效率低。

### 1.2 功能需求

#### FR-1: 问题数据读取（本地 Excel）

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-1.1 | 读取 `black_screen_data/` 目录下最新的 Bug_*.xlsx 文件 | P0 |
| FR-1.2 | 筛选 status=Analysis 的问题列表 | P0 |
| FR-1.3 | 获取单条问题的完整字段（含 Actual Result） | P0 |
| FR-1.4 | 支持多文件合并（多个导出的 Excel） | P1 |
| FR-1.5 | 后续迭代：接入 Trinity 系统（先网页爬虫，API 等 IO 确认） | P2 |

**触发方式:**

| 阶段 | 方式 | 频率 | 数据源 |
|------|------|------|--------|
| 初版 | 手动触发 | 按需 | `black_screen_data/Bug_*.xlsx` |
| 初期 | 定时轮询（Cron） | 每 30 分钟 | Trinity 网页爬虫 → 自动导出 |
| 后续 | 事件驱动 | 问题创建时触发 | Trinity webhook |

**输入:** 项目名称（如 `奇瑞T1Q_8775`）
**输出:** Analysis 状态问题列表，含 Bug ID / Title / Status / Actual Result / Assignee

#### FR-2: Actual Result 信息提取

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-2.1 | 从 Actual Result 列解析问题现象描述 | P0 |
| FR-2.2 | 从 Actual Result 列解析问题发生时间戳 | P0 |
| FR-2.3 | 从 Actual Result 列解析日志 NAS 路径 | P0 |
| FR-2.4 | 从 Actual Result 列解析版本链接（如有） | P1 |
| FR-2.5 | 校验 NAS 路径可达性 | P1 |

**Actual Result 格式示例:**
```
出现开机70秒后还未进入主界面（开机慢问题）
出现问题时间：2026-4-29 13：48
日志链接：\\hzhhnnas01.desaysv.com\DIDA6003\...\邓岳亮\2026-4-30\logs_20260430-110726
版本链接：https://jfrog.desaysv.com/.../2026-04-24_00.01.48_950
```

#### FR-3: 日志自动下载

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-3.1 | 从 NAS UNC 路径下载日志目录到本地 | P0 |
| FR-3.2 | 支持断点续传 / 增量下载 | P2 |
| FR-3.3 | 下载后校验文件完整性 | P1 |
| FR-3.4 | 本地缓存管理（自动清理过期日志） | P2 |
| FR-3.5 | 支持 \\hzhhnnas01 和 \\V01\dfs 两种 NAS 路径格式 | P0 |

**日志目录典型结构:**
```
logs_20260430-110726/
├── bugreport-xxx.zip          # 综合 bugreport (36MB)
├── logcat/                    # Android logcat
├── anr/                       # ANR traces
├── tombstones/                # Native crash tombstones
├── qnx/                       # QNX 系统日志
├── qnx_security/              # QNX 安全日志
├── kernellog/                 # 内核日志
├── mcu/                       # MCU 日志
├── mcu_security/              # MCU 安全日志
├── vehicle_spi_log/           # SPI 通信日志
├── android_tracking/          # Android 追踪日志
├── btlog/                     # 蓝牙日志
├── networklog/                # 网络日志
├── medialog/                  # 媒体日志
├── sysinfo/                   # 系统信息
├── logInfo.txt                # 综合日志文本 (7MB)
├── svdebug_info.txt           # 调试信息
├── bufinfo.txt                # Buffer 信息
└── dropbox.tar.gz             # DropBox 数据
```

#### FR-4: 日志分析引擎

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-4.1 | 按 MCU → QNX → Android 顺序分层分析 | P0 |
| FR-4.2 | 每层分析基于预定义的关键词/规则 | P0 |
| FR-4.3 | 支持时间窗口过滤（根据 Actual Result 中的时间戳） | P0 |
| FR-4.4 | MCU 层：电源状态、SPI 通信、功能安全事件 | P0 |
| FR-4.5 | QNX 层：SAIL/safetymonitor、kernel crash、emac/io-sock、心跳/5501 | P0 |
| FR-4.6 | Android 层：ANR、Native Crash、SurfaceFlinger、logcat 异常 | P0 |
| FR-4.7 | 输出结构化的分析结论（根因分类 + 关键证据 + 置信度） | P0 |
| FR-4.8 | 对无法自动判定的问题，标记为"需人工介入" | P1 |

#### FR-5: 分析报告生成与推送

| ID | 需求 | 优先级 |
|----|------|--------|
| FR-5.1 | 按模板生成 Markdown 分析报告 | P0 |
| FR-5.2 | 报告包含：问题摘要 + 各层分析结果 + 根因推断 + 建议对策 | P0 |
| FR-5.3 | 报告发送给开发确认（Assign 对应的开发人员） | P0 |
| FR-5.4 | 支持报告存档和版本管理 | P1 |
| FR-5.5 | 分析结果可选回写到 Trinity bug 的 Comments | P2 |

### 1.3 非功能需求

| ID | 需求 | 说明 |
|----|------|------|
| NFR-1 | 单问题分析时间 < 5分钟 | 从拉取到报告生成 |
| NFR-2 | 日志下载支持 >100MB 目录 | bugreport.zip 可达 36MB |
| NFR-3 | 分析准确率 ≥ 70% | 与人工分析结论对比 |
| NFR-4 | 支持并发分析 ≥ 3 个问题 | 利用 CrewAI 并行能力 |
| NFR-5 | 错误重试机制 | API 调用、NAS 下载失败自动重试 |

### 1.4 约束条件

| 约束 | 说明 |
|------|------|
| 网络环境 | NAS 在公司内网，需 Windows 域认证 |
| Trinity 系统 | 内部系统，API 文档待确认，优先使用现有访问方式 |
| 技术栈 | Python 3.12 + CrewAI 1.14.x + uv 包管理 |
| 日志格式 | 多为二进制/压缩格式，需解压后分析 |
| 安全合规 | 日志含敏感信息，本地缓存需加密或定期清理 |

---

## 二、软件架构设计

### 2.1 系统分层

```
┌─────────────────────────────────────────────────────────────┐
│                     表现层 (CLI / API)                       │
│  my_crew main.py  ──  crewai run  ──  触发分析任务           │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                   编排层 (CrewAI Flow)                       │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Issue Fetcher│  │Log Downloader│  │ Report Publisher  │  │
│  │    Agent     │  │    Agent     │  │     Agent         │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬──────────┘  │
│         │                 │                    │             │
│  ┌──────▼─────────────────▼────────────────────▼──────────┐ │
│  │              Log Analyzer Crew (层次分析)               │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐     │ │
│  │  │MCU Agent │→│QNX Agent │→│  Android Agent    │     │ │
│  │  └──────────┘  └──────────┘  └──────────────────┘     │ │
│  └────────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      服务层 (Tools)                          │
│  ┌────────────────┐ ┌───────────┐ ┌──────────┐ ┌────────────┐  │
│  │ExcelIssueReader│ │NAS Download│ │LogParser │ │ReportTool  │  │
│  │  (本地Excel)   │ │   Tool    │ │  Tool    │ │(Markdown)  │  │
│  └────────────────┘ └───────────┘ └──────────┘ └────────────┘  │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                      数据层                                  │
│  ┌────────────┐ ┌───────────┐ ┌──────────┐ ┌────────────┐  │
│  │ 本地 Excel │ │ NAS Share │ │本地缓存  │ │ 分析报告   │  │
│  │ Bug_*.xlsx │ │  (外部)   │ │ /cache/  │ │ /reports/  │  │
│  └────────────┘ └───────────┘ └──────────┘ └────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 职责 | 技术 |
|------|------|------|
| **TrinityFetcher** | 对接 Trinity 系统，搜索/筛选/获取 bug | REST API 优先，fallback 网页抓取 |
| **ActualResultParser** | 解析 Actual Result 列，提取描述+时间+路径 | 正则 + 结构化解析 |
| **LogDownloader** | 从 NAS UNC 路径下载日志到本地缓存 | SMB/UNC 协议，支持目录递归 |
| **LogAnalyzer** | 按 MCU→QNX→Android 分层分析日志 | 关键词匹配 + LLM 推理 |
| **MCUAnalyzer** | MCU 日志分析 | 电源、SPI、功能安全事件 |
| **QNXAnalyzer** | QNX 日志分析 | SAIL、kernel、emac、心跳 |
| **AndroidAnalyzer** | Android 日志分析 | ANR、crash、SF、logcat |
| **ReportGenerator** | 生成 Markdown 分析报告 | Jinja2 模板 |
| **ReportPublisher** | 推送报告给开发确认 | 邮件 / Trinity comment / 飞书 |

### 2.3 数据流

```
用户导出 Excel (Trinity → Bug_*.xlsx)
     │
     ▼
┌────────────────┐     ┌──────────────────┐     ┌──────────────┐
│ExcelIssueReader│────→│ ActualResultParser│────→│ LogDownloader│
│ read + filter  │     │ extract paths    │     │ download logs│
│ status=Analysis│     └──────────────────┘     └──────┬───────┘
└────────────────┘                                      │
                                                    │
                    ┌───────────────────────────────┘
                    ▼
          ┌─────────────────┐
          │  LogAnalyzer    │
          │  ┌───────────┐  │
          │  │1.MCU分析  │  │   分析结论
          │  │2.QNX分析  │──┼──────────────┐
          │  │3.Android  │  │              ▼
          │  └───────────┘  │     ┌────────────────┐
          └─────────────────┘     │ReportGenerator │
                                  │ + Publisher    │
                                  └────────┬───────┘
                                           │
                                           ▼
                                    开发人员确认
```

---

## 三、接口设计

### 3.1 问题数据源

**初版: 本地 Excel 文件读取**

数据源: `black_screen_data/Bug_*.xlsx`（用户从 Trinity 手动导出）

```python
ExcelIssueReader:
  - read_latest() → List[BugItem]            # 读取最新导出的 Excel
  - filter_by_status("Analysis") → List[BugItem]
  - get_bug_detail(bug_id: str) → BugDetail
```

**后续: Trinity 系统对接（Phase 5）**

| 方案 | 方式 | 可行性 | 开发量 | 决策 |
|------|------|--------|--------|------|
| A | Trinity REST API | 待与公司IO确认 | 低 | 后续 |
| B | 网页爬虫 | 需处理认证和页面解析 | 高 | **先做** |

```
TrinityTool (Phase 5):
  - search_bugs(project_name: str, status: str = "Analysis") → List[BugItem]
  - get_bug_detail(bug_id: str) → BugDetail
```

### 3.2 Actual Result 解析

```python
@dataclass
class ActualResult:
    description: str       # "出现开机70秒后还未进入主界面（开机慢问题）"
    timestamp: datetime    # 2026-04-29 13:48
    log_path: str          # \\hzhhnnas01.desaysv.com\DIDA6003\...\logs_20260430-110726
    version_link: str      # https://jfrog.desaysv.com/... (optional)
    raw: str               # 原始文本
```

**解析规则:**
- 描述: 第一段文本，到"出现问题时间"之前
- 时间: 正则 `出现问题时间[：:]\s*([\d\- :：]+)`
- 日志路径: 正则 `日志链接[：:]\s*(\\\\[\s\S]+?)(?=\n版本链接|$)`
- 版本链接: 正则 `版本链接[：:]\s*(https?://\S+)`

### 3.3 NAS 日志下载

```
LogDownloader:
  - download_logs(unc_path: str, local_dir: Path) → Path
  - verify_download(local_dir: Path) → bool
  - get_log_structure(local_dir: Path) → LogStructure

LogStructure:
  mcu_logs: List[Path]
  qnx_logs: List[Path]
  android_logs: List[Path]
  bugreport: Path | None
  ...
```

**下载策略:**
- 使用 Windows UNC 路径直接访问（已确认可达）
- 递归复制整个日志目录
- 下载到 `D:\my_crew\cache\logs\{bug_id}\`
- 缓存保留 7 天，定时清理

### 3.4 日志分析引擎

```python
class LogAnalyzer:
    def analyze(self, log_structure: LogStructure,
                issue_context: dict) -> AnalysisResult:
        # Step 1: MCU 层分析
        mcu_result = self.mcu_analyzer.analyze(log_structure.mcu_logs,
                                                issue_context)
        if mcu_result.is_conclusive:
            return AnalysisResult(root_cause=mcu_result, layer="MCU")

        # Step 2: QNX 层分析
        qnx_result = self.qnx_analyzer.analyze(log_structure.qnx_logs,
                                                issue_context,
                                                mcu_context=mcu_result)
        if qnx_result.is_conclusive:
            return AnalysisResult(root_cause=qnx_result, layer="QNX")

        # Step 3: Android 层分析
        android_result = self.android_analyzer.analyze(
            log_structure.android_logs, issue_context,
            mcu_context=mcu_result, qnx_context=qnx_result)
        return AnalysisResult(root_cause=android_result, layer="Android")
```

### 3.5 报告生成

**报告模板结构:**
```markdown
# 黑卡闪问题分析报告

## 基本信息
- Bug ID / 标题 / 状态 / 严重度 / 模块
- 问题发生时间 / 软件版本

## 分析结论
- 根因分类: (基于25类细粒度分类)
- 根因描述
- 置信度: 高/中/低

## 分层分析详情
### MCU 层
- 关键发现 / 异常事件 / 分析依据

### QNX 层
- 关键发现 / 异常事件 / 分析依据

### Android 层
- 关键发现 / 异常事件 / 分析依据

## 建议对策
- 修复建议

## 待确认事项
- 需开发确认的问题点
```

---

## 四、日志分析流程设计

> ⚠️ **待办: 本节内容需协同整理。** 以下为初步框架，具体的分析项、关键词、判定逻辑需与用户一起确认细化。

### 4.1 分析顺序与逻辑

黑屏问题的根因通常遵循从底层到上层的排查逻辑：

```
MCU 层分析
├── 关键词: "电源", "供电", "电流", "限流", "电压", "5A", "10A",
│          "功能安全", "safety", "pshold", "power"
├── 检查项:
│   ├── 电源状态是否异常 (电压波动、电流超限)
│   ├── 功能安全事件 (pshold 拉低 → ramdump)
│   └── MCU 与 SOC 通信 (SPI 状态)
├── 如果发现异常 → 判定为 MCU/电源层问题，终止
└── 如果正常 → 进入 QNX 层分析

    QNX 层分析
    ├── 关键词: "sail", "safetymonitor", "75ms", "ramdump",
    │          "idps", "kernel crash", "emac", "io-sock",
    │          "0x80", "0x5501", "心跳", "5501", "heartbeat",
    │          "NOC error", "DDR", "900E"
    ├── 检查项:
    │   ├── SAIL/safetymonitor 是否超时
    │   ├── IDPS/Kernel 是否 crash
    │   ├── SPI 心跳消息是否丢失 (5501/80)
    │   ├── emac/io-sock 驱动是否异常
    │   └── NOC Error/DDR 错误
    ├── 如果发现异常 → 判定为 QNX 层问题，终止
    └── 如果正常 → 进入 Android 层分析

        Android 层分析
        ├── 关键词: "ANR", "NullPointer", "SIGSEGV", "SIGABRT",
        │          "surfaceflinger", "watchdog", "fatal exception",
        │          "tombstone", "freeze", "冻结", "crash",
        │          "ContentObserver", "observer", "PAG", "动画"
        ├── 检查项:
        │   ├── ANR traces → 哪个组件超时
        │   ├── Native Crash tombstones → signal + backtrace
        │   ├── SurfaceFlinger 异常 → 显示链路
        │   ├── 应用层 crash (NPE, Observer, 跨进程)
        │   ├── PAG/动画库异常
        │   └── 进程 freeze/卡死
        └── 结论 → 生成分析报告
```

### 4.2 时间窗口过滤

根据 Actual Result 中提取的问题发生时间，对日志进行时间窗口过滤：

- 默认窗口: 问题时间前 5 分钟 ~ 问题时间后 2 分钟
- 可配置扩展: 如问题前后各扩展 10 分钟
- 过滤对象: logcat (带时间戳行)、QNX slog2 (带时间戳行)

### 4.3 关键证据提取规则

| 层 | 日志源 | 关键证据 | 判定逻辑 |
|----|--------|----------|----------|
| MCU | mcu/*.log | "pshold=0" | pshold 拉低 → MCU 主动触发复位 |
| MCU | mcu_security/* | "safety fault" | 功能安全故障 |
| MCU | vehicle_spi_log/* | "5501" 缺失 | SPI 通信中断 |
| QNX | qnx/*.log | "SAIL timeout 75ms" | SAIL 响应超时 |
| QNX | qnx/*.log | "kernel crash" | QNX kernel panic |
| QNX | kernellog/* | "NOC error" / "DDR" | 硬件异常 |
| QNX | qnx/io-sock.cor* | emac 异常 | 网络驱动挂死 |
| Android | anr/* | "Input dispatching timed out" | ANR 判定 |
| Android | tombstones/* | "signal 11 (SIGSEGV)" | Native crash |
| Android | logcat/* | "FATAL EXCEPTION" | Java crash |
| Android | logcat/* | "SurfaceFlinger" error | 显示异常 |
| Android | logcat/* | "Too many open files" | FD 泄漏 |

---

## 五、CrewAI Agent/Task 设计

### 5.1 Agent 角色定义

#### Agent 1: Issue Reader（问题读取员）
```yaml
role: 黑卡闪问题数据读取员
goal: 读取本地 Excel 导出的 Bug 数据，筛选 status=Analysis 的问题，解析 Actual Result 列
backstory: |
  你负责从 black_screen_data/ 目录读取最新的 Bug_*.xlsx 文件。
  你知道如何筛选 Analysis 状态的问题，并从 Actual Result 列中
  提取问题描述、时间戳、日志 NAS 路径和版本链接。
tools:
  - excel_issue_reader_tool
  - actual_result_parser_tool
```

#### Agent 2: Log Downloader（日志下载员）
```yaml
role: 日志下载与预处理专家
goal: 根据 Actual Result 中的 NAS 路径，下载完整日志目录到本地，校验完整性
backstory: |
  你知道公司 NAS 的文件结构，能处理 \\hzhhnnas01 和 \\V01\dfs
  两种路径格式。你会递归下载整个日志目录，并验证关键文件是否完整。
tools:
  - nas_download_tool
  - log_validator_tool
```

#### Agent 3: Log Analyzer Crew（日志分析团队）

**MCU 分析员:**
```yaml
role: MCU 层日志分析专家
goal: 分析 MCU 日志，判定电源、SPI 通信、功能安全是否存在异常
backstory: |
  你是车载 MCU 系统的专家，精通 MCU 日志解读。你关注电源状态、
  SPI 通信链路、功能安全事件。你会根据黑屏问题的时间点，
  在 MCU 日志中查找异常信号。
tools:
  - mcu_log_parser_tool
  - keyword_search_tool
```

**QNX 分析员:**
```yaml
role: QNX 层日志分析专家
goal: 分析 QNX 日志，判定 SAIL、kernel、emac、通信是否异常
backstory: |
  你是 QNX 系统的资深工程师，精通 SAIL/safetymonitor、kernel、
  io-sock/emac 驱动。你知道 5501/80 心跳消息是判定黑屏问题的关键信号。
tools:
  - qnx_log_parser_tool
  - keyword_search_tool
```

**Android 分析员:**
```yaml
role: Android 层日志分析专家
goal: 分析 Android 日志，判定应用 crash、ANR、显示异常
backstory: |
  你是 Android 系统的资深工程师，精通 logcat、tombstone、
  ANR trace 分析。你知道 Observer 泄漏是高频问题。
tools:
  - android_log_parser_tool
  - keyword_search_tool
```

#### Agent 4: Report Publisher（报告发布员）
```yaml
role: 分析报告生成与发布员
goal: 将各层分析结果汇总，按模板生成 Markdown 报告，发送给开发确认
backstory: |
  你擅长将技术分析结果整理为清晰的结构化报告。你知道报告的读者
  是开发工程师，需要既有结论又有证据。
tools:
  - report_generator_tool
  - message_sender_tool
```

### 5.2 Task 编排

```
Task 1: read_and_filter_issues
  Agent: Issue Reader
  输入: black_screen_data/Bug_*.xlsx
  输出: List[Issue] (status=Analysis, 含 Actual Result)

Task 2: parse_actual_results  (并行)
  Agent: Issue Reader
  输入: List[Issue]
  输出: List[ParsedIssue] (描述 + 时间 + 路径 + 版本)

Task 3: download_logs  (并行，每个 issue 独立)
  Agent: Log Downloader
  输入: ParsedIssue.log_path
  输出: LogStructure (本地路径)

Task 4: analyze_mcu  (每个 issue)
  Agent: MCU 分析员
  输入: LogStructure.mcu_logs + issue_context
  输出: MCUAnalysisResult

Task 5: analyze_qnx  (依赖 Task 4)
  Agent: QNX 分析员
  输入: LogStructure.qnx_logs + issue_context + MCUAnalysisResult
  输出: QNXAnalysisResult

Task 6: analyze_android  (依赖 Task 5)
  Agent: Android 分析员
  输入: LogStructure.android_logs + issue_context + QNXAnalysisResult
  输出: AndroidAnalysisResult

Task 7: generate_report  (依赖 Task 4/5/6)
  Agent: Report Publisher
  输入: 各层分析结果汇总
  输出: Markdown 报告文件

Task 8: publish_report
  Agent: Report Publisher
  输入: 报告文件 + issue.assignee
  输出: 推送确认
```

### 5.3 文件结构规划

```
D:\my_crew\
├── src/my_crew/
│   ├── config/
│   │   ├── agents.yaml          # 新增 Agent 定义
│   │   └── tasks.yaml           # 新增 Task 定义
│   ├── tools/
│   │   ├── excel_issue_tool.py   # 已有 - Excel 分析
│   │   ├── trinity_tool.py       # 新增 - Trinity 系统对接
│   │   ├── actual_result_parser.py # 新增 - Actual Result 解析
│   │   ├── nas_download_tool.py  # 新增 - NAS 日志下载
│   │   ├── log_analyzer/
│   │   │   ├── __init__.py
│   │   │   ├── base.py           # 分析基类
│   │   │   ├── mcu_analyzer.py   # MCU 层分析
│   │   │   ├── qnx_analyzer.py   # QNX 层分析
│   │   │   ├── android_analyzer.py # Android 层分析
│   │   │   └── rules.py          # 分析规则定义（25类）
│   │   ├── report_generator.py   # 新增 - 报告生成
│   │   └── report_publisher.py   # 新增 - 报告推送
│   ├── crew.py                   # 修改 - 新增 crew 定义
│   └── main.py                   # 修改 - 新增入口
├── cache/
│   └── logs/                     # 日志下载缓存
├── reports/                      # 分析报告存档
├── black_screen_data/            # 已有 - 问题数据
│   ├── Bug_*.xlsx
│   └── deep_analysis_v2.md
└── docs/
    └── architecture.md           # 本文档
```

---

## 六、实施路线图

### Phase 1: 基础工具开发（2-3天）

| 任务 | 内容 | 优先级 |
|------|------|--------|
| P1.1 | ExcelIssueReader: 读取 Bug_*.xlsx，筛选 Analysis 状态 | P0 |
| P1.2 | ActualResultParser: 解析描述 + 时间戳 + NAS路径 + 版本链接 | P0 |
| P1.3 | NAS 下载工具: UNC 路径递归复制日志目录 | P0 |
| P1.4 | 日志解压与文件索引工具 | P0 |

**可验证:** 给定 Bug_*.xlsx，自动筛选 Analysis 问题，下载对应日志到本地

### Phase 2: 日志分析规则（3-4天）

| 任务 | 内容 | 优先级 |
|------|------|--------|
| P2.1 | MCU 层分析规则与工具 | P0 |
| P2.2 | QNX 层分析规则与工具 | P0 |
| P2.3 | Android 层分析规则与工具 | P0 |
| P2.4 | 时间窗口过滤工具 | P1 |

**可验证:** 给定本地日志，能输出结构化的分析结论

### Phase 3: Agent 编排（2-3天）

| 任务 | 内容 | 优先级 |
|------|------|--------|
| P3.1 | CrewAI agents.yaml 定义 | P0 |
| P3.2 | CrewAI tasks.yaml 编排 | P0 |
| P3.3 | 主流程串联与错误处理 | P0 |

**可验证:** 端到端跑通单个问题的分析流程

### Phase 4: 报告与推送（1-2天）

| 任务 | 内容 | 优先级 |
|------|------|--------|
| P4.1 | Markdown 报告模板 | P0 |
| P4.2 | 报告推送（邮件/飞书/Trinity comment） | P0 |

**可验证:** 自动生成报告并推送

### Phase 5: Trinity 对接 + 定时触发（后续迭代）

| 任务 | 内容 | 优先级 |
|------|------|--------|
| P5.1 | Trinity 网页爬虫：登录认证 + 搜索 + 列表抓取 | P2 |
| P5.2 | 问题搜索与筛选（按项目 + 标题关键词 + Status） | P2 |
| P5.3 | Cron 定时任务：每 30 分钟扫描新 Analysis 问题 | P2 |
| P5.4 | 状态回写 + API 切换（待 IO 确认后） | P2 |

**可验证:** 每 30 分钟自动拉取新 Analysis 问题，触发分析流程

### Phase 6: 优化与稳定（持续）

| 任务 | 内容 |
|------|------|
| P6.1 | 分析规则持续优化（基于反馈） |
| P6.2 | 批量分析支持 |
| P6.3 | 定时任务（每日扫描新 Analysis 问题） |
| P6.4 | 分析准确率统计与改进 |

---

## 附录 A: 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Trinity 无 API 接口 | 需改用 Excel 导出/网页爬虫 | 先用 Excel 模式，Phase 5 再探索 |
| NAS 权限不足 | 部分日志无法下载 | 下载前预检查，失败时标记"无法访问" |
| 日志格式不统一 | 分析规则失效 | 多版本正则匹配，LLM fallback |
| LLM 分析幻觉 | 根因误判 | 强制引用日志原文作为证据，低置信度标记 |

## 附录 B: 关键 NAS 路径格式

| 格式 | 示例 | 处理方式 |
|------|------|----------|
| 标准 UNC | `\\hzhhnnas01.desaysv.com\DIDA6003\...` | 直接访问 |
| V01 DFS | `\\V01\dfs\DIDA6003\...` | 映射到相同物理路径 |
| 本地路径（如有） | `D:\logs\...` | 直接访问 |
