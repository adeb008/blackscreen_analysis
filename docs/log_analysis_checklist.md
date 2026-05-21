# 日志分析时间线工具 — 分层确认清单

> 请在各层的「分析内容」「日志文件/目录」「检查关键字」「输出结论」栏填写。
> 已有建议内容供参考，可增删改。
> 
> 填写人: __________  日期: __________

---

## MCU 层

1，电源状态，协议格式：01 51 16 02 00 XX 其中01 51 16 02 00是固定的，xx最后一个Byte是电源状态参考下面的定义
00: STATE OFF/Power off
01: STATE_BG_STARTUP
02: STATE_1H_MODE 1小时模式
03: STATE_DEGRADED/LIMITED(弱电/受限模式)
04: STATE_TOD（TOD)模式
05: NORMAL(正常模式状态）
06: STANDBY（待机状态）
07: STATE_SLEEP（预睡眠状态）
08: FOTA （升级状态）
09: AWAKE状态（SOC断电）
0A: STR状态（SOC休眠）
0B: 本地模式(CAN网络发送器disable)
0C: STARTUP(启动状态，ACC ON且电压正常，开始播开机动画)
例如：在日志里读到的 01 51 16 02 00 06; 06 是待机状态

2，ACC状态，协议格式：03 73 53 05 00 FE 0E 01 02 xx 其中 03 73 53 05 00 FE 0E 01 02 是固定的，XX最后一个byte是ACC的状态，参考以下定义
00:钥匙档位OFF
01:钥匙档位ACC
02:钥匙档位ON
03:钥匙档位start(CRANK+ON)
例如：在日志里读到的: 03 73 53 05 00 FE 0E 01 02， 02是ACC ON

3，档位状态，协议格式：03 73 53 05 00 FE 1A 01 xx ，其中 03 73 53 05 00 FE 1A 是固件的，XX最后一个byte是档位的状态，参考以下定义
01：P档
02：R档
03：N档
04：D档
例如：在日志里读到的  03 73 53 05 00 FE 1A 01 04，04是D档

4，哨兵状态，协议格式：01 51 15 03 00 17 xx，其中01 51 15 03 00 17是固定的，xx最后一个byte是哨兵状态，参考以下定义
00:未激活或退出
01：哨兵激活
02：碰撞事件
例如：在日志里读到的  01 51 15 03 00 17 01，01是消兵激活状态

5，仪表屏背光状态，协议格式：01 51 02 02 00 30，其中 01 51 02 02 00 是固定的，3x是背光的状态，参考以下定义
30:On（亮）
31:OFF（灭）
32:当前亮度值的百分比系数
33:当前亮度输出PWM值
34:当前亮度等级
例如：在日志里读到的 51 02 02 00 30，30表示仪表背光是ON

6，中控屏背光状态，协议格式：01 51 02 02 00 01，其中 01 51 02 02 00是固定的，01 是背光状态，参考以下定义
00：On（亮）
01：OFF（灭））
02：当前亮度值的百分比系数
03：当前亮度输出PWM值
04：当前亮度等级
例如：在日志里读到的 01 51 02 02 00 01，01 表示仪表屏背光是灭的状态

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
