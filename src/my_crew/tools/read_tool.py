from __future__ import annotations

from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class ReadToolInput(BaseModel):
    path: str = Field(..., description="File path to read (absolute or project-relative).")
    start_line: int = Field(1, description="Start line number (1-based).")
    end_line: int = Field(200, description="End line number (inclusive).")


class ReadTool(BaseTool):
    name: str = "read"
    description: str = "Read a text file by line range."
    args_schema: type[BaseModel] = ReadToolInput

    def _run(self, path: str, start_line: int = 1, end_line: int = 200) -> str:
        project_root = Path(__file__).resolve().parents[3]
        p = Path(path)
        if not p.is_absolute():
            p = (project_root / p).resolve()

        if not p.exists():
            return f"Error: file not found: {p}"
        if p.is_dir():
            return f"Error: path is a directory: {p}"

        start = max(1, int(start_line))
        end = max(start, int(end_line))

        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines:
            return ""

        selected = lines[start - 1:end]
        return "\n".join(f"{idx}. {line}" for idx, line in enumerate(selected, start=start))
