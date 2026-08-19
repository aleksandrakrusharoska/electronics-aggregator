import sys
from pathlib import Path

# scrapy_project has no package structure (no __init__.py at the root), so
# modules like run_dedup_agent.py are only importable when scrapy_project
# itself is on sys.path. Running scripts directly (`python run_dedup_agent.py`
# from inside scrapy_project/) gets this for free; pytest collecting from
# tests/ does not.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
