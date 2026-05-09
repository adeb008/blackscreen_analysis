#!/usr/bin/env python
import sys
import warnings
from datetime import datetime
from pathlib import Path

from my_crew.crew import MyCrew

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

DEFAULT_EXCEL_PATH = "D:\my_crew\black_screen_data\Bug_20260508171433.xlsx"


def _inputs() -> dict[str, str]:
    excel_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EXCEL_PATH
    return {
        "topic": "黑卡闪问题提炼分析",
        "current_year": str(datetime.now().year),
        "excel_path": str(Path(excel_path).as_posix()),
    }


def run():
    """Run the crew."""
    try:
        MyCrew().crew().kickoff(inputs=_inputs())
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """Train the crew for a given number of iterations."""
    try:
        MyCrew().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=_inputs())
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    """Replay the crew execution from a specific task."""
    try:
        MyCrew().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    """Test the crew execution and return the results."""
    try:
        MyCrew().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=_inputs())
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")


def run_with_trigger():
    """Run the crew with trigger payload."""
    import json

    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    inputs = _inputs()
    inputs["crewai_trigger_payload"] = trigger_payload

    try:
        return MyCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")