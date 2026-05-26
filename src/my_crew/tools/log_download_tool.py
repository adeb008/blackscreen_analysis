"""日志下载工具 — 从 Actual Result 提取 UNC 路径并下载到本地"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from my_crew.config import get_project_root

LOG_DIR = get_project_root() / "T1Q黑卡闪问题分析"


class LogDownloadInput(BaseModel):
    actual_result: str = Field(..., description="Actual Result 列的原始文本")
    bug_id: str = Field(..., description="Bug ID，用于命名下载目录")
    title: str = Field(default="", description="问题标题，用于命名")


class LogDownloadTool(BaseTool):
    name: str = "spi_log_downloader"
    description: str = (
        "从 Actual Result 列提取日志 NAS 路径，检查权限，下载到本地。"
        "返回 JSON: {bug_id, path, status: ok|no_path|denied|error, local_dir, file_count}"
    )
    args_schema: type[BaseModel] = LogDownloadInput

    def _run(self, actual_result: str, bug_id: str, title: str = "") -> str:
        # 1. 提取路径
        log_path = self._extract_log_path(actual_result)
        if not log_path:
            return self._result(bug_id, "no_path", error="Actual Result中未找到日志路径")

        # 2. 转 bash UNC
        unc_bash = log_path.replace("\\", "/")
        if not unc_bash.startswith("//"):
            unc_bash = "//" + unc_bash.lstrip("/")
        while "//" in unc_bash[2:]:
            unc_bash = unc_bash[:2] + unc_bash[2:].replace("//", "/")

        # 3. 检查权限
        try:
            r = subprocess.run(
                ["ls", unc_bash],
                capture_output=True, text=True, timeout=15
            )
            if r.returncode != 0 or not r.stdout.strip():
                err = r.stderr.strip()
                reason = "无访问权限" if "denied" in err.lower() else (err[:80] or "目录为空")
                return self._result(bug_id, "denied", error=reason, path=log_path)
        except subprocess.TimeoutExpired:
            return self._result(bug_id, "denied", error="连接超时", path=log_path)
        except Exception as e:
            return self._result(bug_id, "error", error=str(e)[:100], path=log_path)

        # 4. 下载
        safe_title = self._sanitize(title) if title else ""
        dirname = f"{bug_id}_{safe_title}" if safe_title else bug_id
        local_dir = LOG_DIR / dirname
        local_dir.mkdir(parents=True, exist_ok=True)

        try:
            src = unc_bash.rstrip("/") + "/."
            cp_result = subprocess.run(
                ["cp", "-r", src, str(local_dir)],
                capture_output=True, text=True, timeout=600
            )
            if cp_result.returncode != 0:
                return self._result(bug_id, "error",
                                    error=f"复制失败: {cp_result.stderr[:100]}",
                                    path=log_path)

            # 统计文件数
            file_count = sum(1 for _ in local_dir.rglob("*") if _.is_file())
            return self._result(bug_id, "ok", path=log_path,
                                local_dir=str(local_dir), file_count=file_count)
        except subprocess.TimeoutExpired:
            return self._result(bug_id, "error", error="下载超时", path=log_path)
        except Exception as e:
            return self._result(bug_id, "error", error=str(e)[:100], path=log_path)

    # ── 辅助 ──

    def _extract_log_path(self, text: str) -> str:
        if not text:
            return ""
        m = re.search(r"日志链接[：:]\\s*(.+)", text)
        if not m:
            m = re.search(r"日志地址[：:]\\s*(.+)", text)
        if not m:
            m = re.search(r"log链接[：:]\\s*(.+)", text)
        if not m:
            return ""

        raw = m.group(1).strip()
        raw = re.split(r"[\n\r]|出现问题时间|版本链接|视频链接", raw)[0].strip()
        raw = re.sub(r"[。，,;]+$", "", raw)
        # Excel中UNC路径 \ 被存为 \\，归一化
        return raw.replace("\\\\", "\\")

    def _sanitize(self, s: str) -> str:
        for ch in r"/\:*?\"<>|":
            s = s.replace(ch, "_")
        return s[:60]

    def _result(self, bug_id: str, status: str, **kwargs) -> str:
        import json
        return json.dumps({"bug_id": bug_id, "status": status, **kwargs},
                          ensure_ascii=False)
