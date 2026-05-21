"""项目路径 — 自动检测，消除硬编码

所有模块 import: from my_crew.paths import PROJECT_ROOT
"""

from pathlib import Path

# 本项目: src/my_crew/paths.py → 往上3级 = 项目根
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 常用子目录
BLACK_SCREEN_DATA = PROJECT_ROOT / "black_screen_data"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
DOCS_DIR = PROJECT_ROOT / "docs"

# 关键文件
KB_PATH = BLACK_SCREEN_DATA / "analyzed_bugs.json"
DEFAULT_EXCEL = BLACK_SCREEN_DATA  # 运行时自动找最新的 Bug_*.xlsx
