"""Parameterised read-only lookups used by the application (coach market context).

All values are passed as query parameters (%s): never interpolated into SQL.
"""

from __future__ import annotations

import psycopg

SKILL_DEMAND_SQL = """
WITH ref_base AS (
    SELECT job_id FROM market.jobs_reference
    WHERE NOT skills_missing AND (%(role)s::text IS NULL OR role_family = %(role)s)
), ref AS (
    SELECT s.name, COUNT(*) AS postings
    FROM ref_base b
    JOIN market.job_skills_reference js ON js.job_id = b.job_id
    JOIN market.skills s ON s.skill_id = js.skill_id
    WHERE s.name = ANY(%(skills)s)
    GROUP BY s.name
), live AS (
    SELECT s.name, COUNT(*) AS postings
    FROM market.jobs_live j
    JOIN market.job_skills_live js ON js.job_id = j.job_id
    JOIN market.skills s ON s.skill_id = js.skill_id
    WHERE s.name = ANY(%(skills)s) AND j.is_tech
    GROUP BY s.name
)
SELECT q.name,
       COALESCE(ref.postings, 0)                                        AS reference_postings,
       (SELECT COUNT(*) FROM ref_base)                                  AS reference_total,
       COALESCE(live.postings, 0)                                       AS live_tech_postings,
       (SELECT COUNT(*) FROM market.jobs_live WHERE is_tech)            AS live_tech_total
FROM unnest(%(skills)s::text[]) AS q(name)
LEFT JOIN ref  ON ref.name = q.name
LEFT JOIN live ON live.name = q.name
"""


def skill_demand(conn: psycopg.Connection, skills: list[str], role_family: str | None = None) -> list[dict]:
    """Share of postings mentioning each skill, per source (never pooled).

    reference = data_jobs 2023, optionally restricted to one role family;
    live      = tech postings of the Arbeitnow snapshot.
    """
    rows = conn.execute(SKILL_DEMAND_SQL, {"skills": list(skills), "role": role_family}).fetchall()
    result = []
    for name, ref_n, ref_total, live_n, live_total in rows:
        result.append({
            "skill": name,
            "reference_postings": ref_n,
            "reference_share_pct": round(100 * ref_n / ref_total, 2) if ref_total else None,
            "live_tech_postings": live_n,
            "live_tech_share_pct": round(100 * live_n / live_total, 2) if live_total else None,
        })
    return result


def role_families(conn: psycopg.Connection) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT role_family FROM market.jobs_reference ORDER BY role_family").fetchall()]
