"""Streamlit Community Cloud entrypoint.

Cloud expects a top-level ``streamlit_app.py`` (or you specify the path in the
deploy UI). This module is a thin re-export — the real app lives in
``frontend/app.py``.
"""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).parent / "frontend" / "app.py"), run_name="__main__")
