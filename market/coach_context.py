"""Build the small market-context file used by the AI Interview Coach.

    python -m market.coach_context

Reads the validated Tableau extract dashboard/tableau/data/ref_skill_demand_2023.csv
(itself exported from PostgreSQL, see market/dashboard/export.py) and writes
app/market_context/skill_demand_2023.json: for each role family, the number of
postings with skill data and, for every skill of the coach taxonomy, the number
of postings that ask for it.

Why a JSON file and not a database query: the coach must keep working offline
and in its Docker image without PostgreSQL. The file is ~10 KB, versioned, and
regenerated from the same validated numbers as the dashboard.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from market import PROJECT_ROOT

SOURCE_CSV = PROJECT_ROOT / "dashboard" / "tableau" / "data" / "ref_skill_demand_2023.csv"
OUT_FILE = PROJECT_ROOT / "app" / "market_context" / "skill_demand_2023.json"
GROUP_COLUMNS = ["role_family", "seniority", "country_group", "remote"]


def build_context(source_csv: Path = SOURCE_CSV) -> dict:
    df = pd.read_csv(source_csv)
    # The extract is dense (every skill x group row exists) and each row carries
    # its group's denominator, so per-role totals are plain sums.
    postings = df.drop_duplicates(GROUP_COLUMNS).groupby("role_family")["postings_in_group"].sum()
    coach = df[df["in_coach_taxonomy"]]
    counts = coach.groupby(["role_family", "skill"])["postings_with_skill"].sum()
    roles = {
        role: {
            "postings": int(postings[role]),
            "skills": {skill: int(n) for skill, n in counts[role].sort_values(ascending=False).items()},
        }
        for role in sorted(postings.index)
    }
    return {
        "source": "lukebarousse/data_jobs (Hugging Face, Apache-2.0)",
        "period": "2023",
        "population": "Data and tech job postings with skill data, worldwide",
        "generated_from": source_csv.relative_to(PROJECT_ROOT).as_posix(),
        "total_postings": int(postings.sum()),
        "roles": roles,
    }


def main() -> None:
    context = build_context()
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(context, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{OUT_FILE.relative_to(PROJECT_ROOT)}: {len(context['roles'])} role families, "
          f"{context['total_postings']:,} postings")


if __name__ == "__main__":
    main()
