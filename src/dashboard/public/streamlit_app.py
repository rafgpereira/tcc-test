"""Entry point of the public copy of the dashboard on Streamlit Community Cloud.

The cloud runs ``streamlit run src/dashboard/public/streamlit_app.py`` from a clone of the
repository, with the packages listed in ``requirements.txt`` next to this file. Here the code in
``src/`` becomes importable, the working folder becomes the repository root (the dashboard reads
``data/`` from there), the packages are unzipped once per server (``dashboard.cloud``) and the same
app as ``python -m dashboard serve`` opens.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
os.chdir(ROOT)

import streamlit as st

from dashboard import app, cloud, config


@st.cache_resource(show_spinner="descompactando os resultados (só na primeira abertura)...")
def _prepare() -> list[str]:
    return cloud.prepare(ROOT)


_prepare()
os.environ.setdefault(config.ENV_EVALUATION_DIR, str(config.DEFAULT_EVALUATION_DIR))
app.main()
