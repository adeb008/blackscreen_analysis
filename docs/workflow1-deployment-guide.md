# 黑卡闪问题分析 - 工作流一部署与使用指南

> 项目：my_crew v3.2  
> 更新：2026-05-23  
> 维护：uidq1474（本地开发）/ uidq2071（服务器部署）

---

## 一、整体架构

```
本地PC（uidq1474）
  └── D:\my_crew\
        ├── Excel原始数据（黑卡闪问题清单）
        ├── CrewAI工作流一（refinement）
        │     ├── issue_refiner Agent（分类精校 + 经验库读写）
        │     └── report_writer Agent（报告生成 + 经验查重）
        └── .env（API密钥 + 服务器地址）

内网服务器（10.219.9.92 / uidq2071）
  └── /workspace/uidq2071/huihong_dir/my_crew/
        ├── db/experience.db          ← SQLite经验库
        ├── src/api_server.py         ← FastAPI服务（端口8765）
        ├── src/manage_api.sh         ← 服务管理脚本
        └── logs/api.log              ← API运行日志
```

工作流一闭环：

```
Excel输入 → issue_refiner（查经验库 → 精校分类 → 回写经验库）
         → report_writer（查经验库去重 → 生成报告）
         → outputs/report.html
```

---

## 二、服务器经验库管理

### 启动 / 停止 / 查状态

```bash
# SSH连接服务器
ssh uidq2071@10.219.9.92

# 启动API服务
bash /workspace/uidq2071/huihong_dir/my_crew/src/manage_api.sh start

# 停止
bash /workspace/uidq2071/huihong_dir/my_crew/src/manage_api.sh stop

# 查状态
bash /workspace/uidq2071/huihong_dir/my_crew/src/manage_api.sh status

# 重启
bash /workspace/uidq2071/huihong_dir/my_crew/src/manage_api.sh restart
```

### 健康检查

浏览器或curl访问：

```
http://10.219.9.92:8765/health
```

返回 `{"status":"ok"}` 表示正常。

### Swagger API文档

```
http://10.219.9.92:8765/docs
```

内网任意机器均可访问，可在线测试所有接口。

### 注意事项

- 服务器重启后需手动执行 `manage_api.sh start`（未配置开机自启）
- 建议联系管理员将启动命令加入 `crontab @reboot`
- 数据库路径：`/workspace/uidq2071/huihong_dir/my_crew/db/experience.db`
- API日志路径：`/workspace/uidq2071/huihong_dir/my_crew/logs/api.log`
- 磁盘剩余约83GB（96%占用），注意空间

---

## 三、本机运行工作流一

### 前置条件

1. 已安装 Python 3.10+ 和 uv
2. 已克隆仓库到本地
3. 已配置 `.env` 文件（见第四节）
4. 服务器经验库API运行中（`http://10.219.9.92:8765/health` 正常）

### 运行命令

```bash
cd D:\my_crew

# 默认运行（增量模式，只处理新问题）
uv run crewai run

# 强制全量重跑（重新分析所有数据）
set FORCE_FULL_RUN=1
uv run crewai run

# 只运行工作流一（refinement，不下载新数据）
uv run python -m my_crew.main refine

# 只运行工作流二（download，下载更新数据）
uv run python -m my_crew.main download

# 完整流程（download + refine）
uv run python -m my_crew.main full
```

### 输出文件

| 文件 | 说明 |
|------|------|
| `outputs/report.html` | 主分析报告（浏览器打开） |
| `outputs/analyzed_bugs.json` | 已分析问题闭环数据库 |
| `outputs/pending_categories.json` | LLM提议的新分类（待合并） |
| `logs/run.log` | 运行日志 |

---

## 四、.env 配置说明

`.env` 文件位于 `D:\my_crew\.env`，必填字段：

```env
# LLM API密钥（DeepSeek，走Anthropic兼容接口）
DEEPSEEK_ANTHROPIC_API_KEY=<你的密钥>
ANTHROPIC_BASE_URL=https://api.deepseek.com

# 经验库API地址（服务器）
EXPERIENCE_API_URL=http://10.219.9.92:8765

# 可选：强制全量运行
# FORCE_FULL_RUN=1
```

> 注：`.env` 不提交到git仓库，每人自行配置。

---

## 五、新同事接入步骤

```bash
# 1. 克隆仓库
git clone <仓库地址> D:\my_crew
cd D:\my_crew

# 2. 安装依赖
uv sync

# 3. 配置环境变量
# 复制模板并填入自己的API密钥
copy .env.example .env
# 编辑 .env，填入 DEEPSEEK_ANTHROPIC_API_KEY

# 4. 将待分析Excel放入数据目录
# 格式参考 data/README.md

# 5. 运行
uv run crewai run
```

**共享经验库无需额外配置**，`.env` 里的 `EXPERIENCE_API_URL` 默认指向内网服务器，所有人共用同一个知识库，分析结果会自动回写并积累。

---

## 六、经验库工作原理

### 两个工具

| 工具 | 调用时机 | 作用 |
|------|----------|------|
| `ExperienceMatchTool`（经验库检索） | 精校前、报告生成前 | 检索历史相似问题的分类经验 |
| `ExperienceUpdateTool`（经验库更新） | 精校完成后 | 将本次精校结果回写，更新置信度 |

### 精校三步骤（issue_refiner Agent）

1. **步骤1 - 查库**：调用 `ExperienceMatchTool`，检索历史相似问题的分类经验
2. **步骤2 - 精校**：结合经验库结果，对问题重新分类，与历史经验保持一致或提出更优分类
3. **步骤3 - 回写**：调用 `ExperienceUpdateTool`，将本次精校结果存入经验库，更新置信度

### 积累效果

- 经验库越用越准：每次精校都会回写，置信度逐渐提升
- 跨项目共享：T1Q / T1G 等不同项目的问题共用一个经验库
- 新问题触发新分类：LLM识别出新类型时，写入 `pending_categories.json` 待人工确认后合并

---

## 七、经验库API接口说明

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/experiences/search` | POST | 检索相似经验 |
| `/experiences/update` | POST | 新增/更新经验 |
| `/experiences/list` | GET | 列出所有经验 |
| `/stats` | GET | 统计信息 |

完整文档见：`http://10.219.9.92:8765/docs`

---

## 八、常见问题

**Q: 运行时报 `Connection refused` 或 `ExperienceMatchTool` 调用失败？**  
A: 经验库API没有启动，登录服务器执行 `manage_api.sh start`。工具内建降级逻辑，API不可用时会跳过经验匹配、继续运行，不影响主流程。

**Q: 想查看经验库积累了多少数据？**  
A: 访问 `http://10.219.9.92:8765/stats`，或打开Swagger文档用 `/experiences/list` 查询。

**Q: 新项目（如T2X）怎么接入？**  
A: 直接运行 `uv run crewai run` 即可，经验库按问题内容匹配，不区分项目，会自动学习新项目的问题特征。

**Q: 经验库数据需要备份吗？**  
A: 建议定期备份 `/workspace/uidq2071/huihong_dir/my_crew/db/experience.db`。可以用scp复制到本地存档。

**Q: 磁盘空间不足怎么办？**  
A: 服务器 `/workspace/uidq2071` 目前83GB剩余，experience.db短期内不会撑满。如outputs目录积累太多报告，可手动清理旧文件。

---

## 九、后续升级规划

| 阶段 | 触发条件 | 升级内容 |
|------|----------|----------|
| 当前 | 1-5人使用 | SQLite + FastAPI，轻量够用 |
| 中期 | 5-20人并发 | 迁移至 PostgreSQL，支持更高并发 |
| 远期 | 经验库>1万条 | 加 pgvector 向量检索，提升相似度匹配精度 |

---

*最后更新：2026-05-23 / 作者：uidq1474*
