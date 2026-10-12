"""Load analysis tables from PostgreSQL (read-only role, DATABASE_URL)."""

from __future__ import annotations

import pandas as pd

from market.db.config import connect

REFERENCE_SQL = """
SELECT job_id, role_family, is_senior, work_from_home, country, schedule, posted_month,
       salary_year_avg, skills_missing, skill_count, programming_skill_count, cloud_skill_count,
       libraries_skill_count, databases_skill_count, analyst_tools_skill_count, other_skill_count
FROM market.jobs_reference
"""

REFERENCE_SKILLS_SQL = """
SELECT js.job_id, s.name AS skill
FROM market.job_skills_reference js JOIN market.skills s ON s.skill_id = js.skill_id
WHERE s.name = ANY(%s)
"""

LIVE_SQL = """
SELECT job_id, job_family, is_tech, remote, experience_level, seniority_from_title, description_language,
       description_words, skill_count, tech_skill_count, soft_skill_count
FROM market.jobs_live
"""


def query_df(sql: str, params=None, env_var: str = "DATABASE_URL") -> pd.DataFrame:
    with connect(env_var) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def reference_jobs() -> pd.DataFrame:
    df = query_df(REFERENCE_SQL)
    numeric = [c for c in df.columns if c.endswith("_count")] + ["salary_year_avg"]
    df[numeric] = df[numeric].astype("float64")  # Decimal/NULL -> float/NaN for SciPy
    return df


def reference_skill_matrix(skills: list[str]) -> pd.DataFrame:
    """One boolean column per skill (only for postings with skill data)."""
    links = query_df(REFERENCE_SKILLS_SQL, (skills,))
    return pd.crosstab(links["job_id"], links["skill"]).astype(bool)


def live_jobs() -> pd.DataFrame:
    df = query_df(LIVE_SQL)
    return df.astype({c: "float64" for c in df.columns if c.endswith("_count") or c == "description_words"})
