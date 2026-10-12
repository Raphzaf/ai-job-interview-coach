"""Run every named query of sql/analysis_queries.sql and save the results.

    python -m market.db.run_queries          # uses DATABASE_URL (read-only role)

Results: data/processed/sql_results/<name>.csv + summary.json (runtime, rows).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd

from market import PROCESSED_DIR
from market.db.config import connect

SQL_FILE = Path(__file__).resolve().parents[2] / "sql" / "analysis_queries.sql"
OUT_DIR = PROCESSED_DIR / "sql_results"


def parse_queries(text: str) -> list[dict]:
    """Split the file on '-- name:' markers; keep the question line as metadata."""
    blocks = re.split(r"^-- name:\s*", text, flags=re.MULTILINE)[1:]
    queries = []
    for block in blocks:
        name, _, body = block.partition("\n")
        question = re.search(r"^-- question:\s*(.+)$", body, flags=re.MULTILINE)
        sql = "\n".join(line for line in body.splitlines() if not line.strip().startswith("--")).strip()
        queries.append({"name": name.strip(), "question": question.group(1).strip() if question else "", "sql": sql})
    return queries


def run_all(env_var: str = "DATABASE_URL", out_dir: Path = OUT_DIR) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []
    with connect(env_var) as conn:
        for q in parse_queries(SQL_FILE.read_text(encoding="utf-8")):
            started = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute(q["sql"])
                columns = [d.name for d in cur.description]
                df = pd.DataFrame(cur.fetchall(), columns=columns)
            df.to_csv(out_dir / f"{q['name']}.csv", index=False)
            summary.append({"name": q["name"], "question": q["question"], "rows": len(df),
                            "seconds": round(time.perf_counter() - started, 3)})
            print(f"{q['name']}: {len(df)} rows in {summary[-1]['seconds']}s")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


if __name__ == "__main__":
    run_all()
