"""Job Market Intelligence layer (layer 1 of the AI Job Market & Interview Coach).

Pipeline: public JSON API / reference dataset -> raw files (data/raw)
-> pandas/NumPy cleaning + features -> processed tables (data/processed)
-> PostgreSQL (Phase 3) -> statistics, ML, dashboard.
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
