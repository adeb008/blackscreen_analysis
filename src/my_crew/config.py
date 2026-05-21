"""项目路径配置 — 单点管理，消除硬编码

用法:
  from my_crew.config import get_project_root, get_data_dir, get_output_dir

所有路径都从这里派生，不要在任何其他文件中硬编码 `D:/my_crew/`。
"""

import os
from pathlib import Path


def get_project_root() -> Path:
    """自动检测项目根目录

    优先级:
      1. 环境变量 PROJECT_ROOT
      2. 从当前文件向上查找包含 pyproject.toml 的目录
      3. 当前工作目录
    """
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        return Path(env_root)

    # 从本文件向上找 pyproject.toml
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / "pyproject.toml").exists():
            return current
        current = current.parent

    # 兜底：当前工作目录
    return Path.cwd()


def get_data_dir() -> Path:
    """Bug 数据目录"""
    return get_project_root() / "black_screen_data"


def get_output_dir() -> Path:
    """产物输出目录"""
    return get_project_root() / "outputs"


def get_kb_path() -> Path:
    """闭环知识库路径"""
    path = os.getenv("KB_PATH")
    if path:
        return Path(path)
    return get_data_dir() / "analyzed_bugs.json"


def get_excel_path() -> str | None:
    """最新的 Bug Excel 文件路径（如果存在）"""
    path = os.getenv("EXCEL_PATH")
    if path:
        return path
    data_dir = get_data_dir()
    if not data_dir.exists():
        return None
    xlsx_files = sorted(
        [f for f in data_dir.glob("Bug_*.xlsx") if not f.name.startswith("~$")],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return str(xlsx_files[0]) if xlsx_files else None


def get_nas_mount() -> str:
    """NAS 挂载路径（Windows UNC 或 Linux mount 点）"""
    return os.getenv("NAS_MOUNT_PATH", "//hzhhnnas01.desaysv.com/DIDA6003")


# ── 常量（从环境变量读取，有默认值） ──
PROJECT_ROOT = get_project_root()
DATA_DIR = get_data_dir()
OUTPUT_DIR = get_output_dir()
KB_PATH = get_kb_path()
