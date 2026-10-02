"""Compatibility entry point for the maintained extraction pipeline."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("prepare_question_bank.py")), run_name="__main__")
