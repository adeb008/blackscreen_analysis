# 日志分析时间线工具 — 分层确认清单

> 请在各层的「分析内容」「日志文件/目录」「检查关键字」「输出结论」栏填写。
> 已有建议内容供参考，可增删改。
> 
> 填写人: __________  日期: __________

---

## MCU 层

| 序号 | 分析内容 | 日志文件/目录 | 检查关键字 | 匹配后判定结论 | 优先级 |
|:--:|----------|---------------|-----------|---------------|:--:|
| 1 | SPI 重启事件解析 | `vehicle_spi_log/*.log` 或 `spi_decode/` | 协议头 `01 79 30 09 00` + 原因码 (见116条REASON_MAP) | 输出重启原因码 + 时间 | 高 |
| 2 | SPI 通信超时 | `vehicle_spi_log/*.log` | `SPI.*timeout` / `spi.*resend` / `0x2D` `0x2E` `0x2F` | MCU检测到SPI通信异常 | 高 |
| 3 | 1HZ 心跳超时 | `mcu/*.log` | `1HZ.*timeout` / `1HZ.*超时` / `heartbeat.*loss` | 心跳丢失30秒触发重启 | 高 |
| 4 | 功能安全事件 | `mcu_security/*.log` | `safety fault` / `SAFE_RESET` / `pshold` / `PMA_GPIO_2` | 功能安全触发复位 | 高 |
| 5 | 电源状态 | `mcu/*.log` | `VDD_VSYS` / `bat:` / `电压` / `current` / `5A` / `10A` | 电源异常导致黑屏 | 中 |
| 6 | | | | | |
| 7 | | | | | |
| 8 | | | | | |

**补充说明:**

---

## QNX 层

| 序号 | 分析内容 | 日志文件/目录 | 检查关键字 | 匹配后判定结论 | 优先级 |
|:--:|----------|---------------|-----------|---------------|:--:|
| 1 | SAIL/safetymonitor 超时 | `qnx/*.log` `qnx_security/` | `SAIL.*75ms` / `safetymonitor.*timeout` / `safety_monitor` | SAIL响应超时导致900E | 高 |
| 2 | IDPS / Kernel Crash | `qnx/*.log` `kernellog/` | `idps` / `nidps` / `kernel crash` / `kernel shutdown` | QNX kernel异常 | 高 |
| 3 | NOC Error / DDR | `qnx/*.log` `kernellog/` | `NOC error` / `DDR.*fail` / `900E` / `0xac12e0` | 硬件DDR异常 | 高 |
| 4 | emac / io-sock 驱动 | `qnx/*.log` | `emac.*error` / `io-sock` / `驱动挂死` | 网络驱动异常 | 高 |
| 5 | SPI心跳 / 5501 | `qnx/*.log` | `0x80.*0x5501` / `5501.*80` / `SPI.*heartbeat` | SPI心跳消息丢失 | 高 |
| 6 | STR 休眠唤醒 | `qnx/*.log` `kernellog/` | `STR.*enter` / `STR.*exit` / `suspend` / `resume` / `sleep mode` | STR时序异常 | 中 |
| 7 | QNX 进程/CPU状态 | `qnx/*.log` | `CPU states:` / `pid tid` / `Memory:` / `qvm` | 系统负载异常 | 中 |
| 8 | serdes/显示屏 | `qnx/*.log` | `serializer` / `deserializer` / `串化器` / `解串器` / `DSI` | 显示链路异常 | 中 |
| 9 | | | | | |
| 10 | | | | | |

**补充说明:**

---

## Android 层

| 序号 | 分析内容 | 日志文件/目录 | 检查关键字 | 匹配后判定结论 | 优先级 |
|:--:|----------|---------------|-----------|---------------|:--:|
| 1 | ANR 无响应 | `anr/*` | `ANR` / `Input dispatching timed out` / `Broadcast of intent` | 应用/系统无响应 | 高 |
| 2 | Native Crash | `tombstones/*` | `signal 11 (SIGSEGV)` / `SIGABRT` / `FATAL SIGNAL` / `backtrace` | Native层崩溃 | 高 |
| 3 | Java Crash | `logcat/*` | `FATAL EXCEPTION` / `AndroidRuntime` / `NullPointerException` | Java层崩溃 | 高 |
| 4 | SurfaceFlinger | `logcat/*` | `SurfaceFlinger` / `Too many open files` / `BufferQueue` / `fence` | 显示链路异常 | 高 |
| 5 | 进程CPU/内存(top) | `logInfo.txt` `sysinfo/` | `top -b` / `CPU.*user` / `Mem:` / `PID.*USER` | 资源占用异常 | 中 |
| 6 | Watchdog | `logcat/*` | `WATCHDOG` / `watchdog` | 系统卡死 | 高 |
| 7 | ContentObserver | `logcat/*` | `ContentObserver` / `observer` / `register` / `unregister` | Observer泄漏 | 中 |
| 8 | PAG/动画 | `logcat/*` | `PAG` / `pag` / `lottie` / `动画` / `libpag` | 动画库异常 | 中 |
| 9 | | | | | |
| 10 | | | | | |

**补充说明:**

---

## 全局配置

| 配置项 | 值 |
|--------|-----|
| 默认时间窗口 | 问题时间前 __ 分钟 ~ 后 __ 分钟 |
| 严重事件高亮色 | #f85149 (红) |
| 警告事件颜色 | #d2991d (橙) |
| 信息事件颜色 | #58a6ff (蓝) |
| 输出格式 | ☐ HTML 时间线 / ☐ Markdown 报告 / ☐ JSON / ☐ Excel |
| 是否需要截图嵌入 | ☐ 是 / ☐ 否 |

---

## 判定规则（可选自定义）

| 规则ID | 条件 | 结论模板 |
|--------|------|----------|
| R1 | MCU无异常 → QNX无异常 → Android有ANR/Crash | 「Android应用层异常导致黑屏，MCU和QNX层正常」 |
| R2 | MCU有SPI超时(2D/2E/2F) → QNX无日志 | 「SPI通信中断导致MCU拉SOC重启，QNX侧无法输出日志」 |
| R3 | MCU有1HZ超时 → QNX SPI心跳正常 | 「SOC异常导致1HZ心跳丢失，MCU触发复位」 |
| R4 | | |
| R5 | | |

---

## 其他

**是否需要以下功能:**
- ☐ 时间线图中显示 CAN 总线信号（车速/ACC/挡位）
- ☐ 自动标注「黑屏发生点」
- ☐ 对比正常时段 vs 异常时段的 CPU/内存差异
- ☐ 自动生成「问题还原描述」（自然语言总结）
- ☐ 导出为 PDF

**补充:**
