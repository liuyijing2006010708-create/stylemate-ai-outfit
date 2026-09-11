"""Streamlit Community Cloud entrypoint: visitors supply their own API keys."""

import runpy
from pathlib import Path


runpy.run_path(
    str(Path(__file__).with_name("app.py")),
    init_globals={"PUBLIC_DEPLOYMENT": True},
    run_name="__main__",
)
