"""Load the Phase-2 processed tables into PostgreSQL.

    python -m market.db.load            # needs DATABASE_OWNER_URL

- Idempotent: TRUNCATE + reload inside ONE transaction. A failure leaves the
  previous content untouched (rollback).
- Bulk loading with COPY (fast enough for the 3.5M reference job-skill rows).
- After loading, row counts are compared with the Phase-2 reports; any
  mismatch aborts the transaction.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
import psycopg

from market import PROCESSED_DIR, RAW_DIR
from market.db.config import connect

LIVE_COLUMNS = [
    "job_id", "source_id", "company_id", "slug", "url", "title", "location", "city", "remote", "posted_at",
    "job_family", "is_tech", "experience_level", "experience_level_ambiguous", "seniority_from_title", "schedule",
    "contract_type", "probable_repost", "description_language", "description_chars", "description_words",
    "skill_count", "tech_skill_count", "soft_skill_count", "programming_language_count", "cloud_devops_skill_count",
    "ai_ml_skill_count", "data_skill_count", "requires_english", "requires_german", "tags", "job_types_raw",
]
REF_SKILL_TYPES = ["programming", "cloud", "libraries", "databases", "analyst_tools", "other", "os",
                   "webframeworks", "async", "sync"]
REF_COLUMNS = [
    "job_id", "source_id", "company_id", "job_title", "job_title_short", "role_family", "is_senior",
    "title_seniority", "job_location", "country", "country_repaired", "search_location", "job_via", "schedule",
    "work_from_home", "no_degree_mention", "health_insurance", "posted_at", "posted_month", "salary_rate",
    "salary_year_avg", "salary_hour_avg", "skills_missing", "skill_count",
    *[f"{t}_skill_count" for t in REF_SKILL_TYPES],
]


def _copy_csv(cur: psycopg.Cursor, table: str, df: pd.DataFrame, chunk: int = 200_000) -> None:
    """COPY a DataFrame through CSV text (NULL = empty unquoted field)."""
    cols = ", ".join(df.columns)
    with cur.copy(f"COPY market.{table} ({cols}) FROM STDIN WITH (FORMAT csv)") as copy:
        for start in range(0, len(df), chunk):
            buf = io.StringIO()
            df.iloc[start:start + chunk].to_csv(buf, index=False, header=False)
            copy.write(buf.getvalue())


def _copy_rows(cur: psycopg.Cursor, table: str, df: pd.DataFrame) -> None:
    """COPY row by row (lets psycopg adapt Python lists to text[] arrays)."""
    cols = ", ".join(df.columns)
    with cur.copy(f"COPY market.{table} ({cols}) FROM STDIN") as copy:
        for row in df.itertuples(index=False):
            copy.write_row([None if (not isinstance(v, list) and pd.isna(v)) else v for v in row])


def _int_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    # pandas stores integer columns with NaN as float ("5.0"), which COPY would
    # reject for smallint: convert to nullable integers first.
    for c in columns:
        df[c] = df[c].astype("Int64")
    return df


def read_sources(processed_dir: Path = PROCESSED_DIR, raw_dir: Path = RAW_DIR) -> pd.DataFrame:
    reports = processed_dir / "reports"
    live_report = json.loads((reports / "arbeitnow.json").read_text())
    ref_report = json.loads((reports / "data_jobs.json").read_text())
    live_manifest = live_report["manifest"]
    ref_manifest = json.loads((raw_dir / "hf_data_jobs" / "manifest.json").read_text())
    return pd.DataFrame([
        {"source_id": "arbeitnow", "name": "Arbeitnow Job Board API", "url": live_manifest["url"],
         "license": "Arbeitnow API terms of service (free public API, link back)",
         "version": live_report["snapshot"], "collected_at": live_manifest["started_at_utc"],
         "raw_rows": live_report["raw_profile"]["rows"], "clean_rows": live_report["processed_profile"]["rows"]},
        {"source_id": "data_jobs_2023", "name": "lukebarousse/data_jobs", "url": ref_manifest["source"],
         "license": ref_manifest["license"], "version": ref_manifest["revision"],
         "collected_at": ref_manifest["downloaded_at_utc"],
         "raw_rows": ref_report["raw_profile"]["rows"], "clean_rows": ref_report["processed_profile"]["rows"]},
    ])


def load(processed_dir: Path = PROCESSED_DIR, raw_dir: Path = RAW_DIR, env_var: str = "DATABASE_OWNER_URL") -> dict:
    started = time.time()
    live_dir, ref_dir, reports = processed_dir / "arbeitnow", processed_dir / "data_jobs", processed_dir / "reports"
    sources = read_sources(processed_dir, raw_dir)
    live = pd.read_csv(live_dir / "jobs.csv")
    live_skills = pd.read_csv(live_dir / "job_skills.csv")
    ref = pd.read_csv(ref_dir / "jobs.csv.gz", low_memory=False)
    ref_skills = pd.read_csv(ref_dir / "job_skills.csv.gz")
    vocab = pd.read_csv(processed_dir / "skills.csv")
    descriptions_path = live_dir / "descriptions.csv.gz"
    descriptions = pd.read_csv(descriptions_path) if descriptions_path.exists() else None

    # --- dimensions --------------------------------------------------------------------
    companies = pd.Series(pd.concat([live["company_name"], ref["company_name"]]).dropna().str.strip().unique())
    companies = companies[companies != ""].sort_values().reset_index(drop=True)

    skills = vocab[["skill", "category", "in_coach_taxonomy"]].rename(columns={"skill": "name"}).reset_index(drop=True)
    missing = set(live_skills["skill"]) | set(ref_skills["skill"])
    missing -= set(skills["name"])
    if missing:
        raise RuntimeError(f"{len(missing)} skills used by job_skills are absent from skills.csv: {sorted(missing)[:10]}")

    with connect(env_var) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE market.job_skills_reference, market.job_skills_live, market.job_descriptions, "
                    "market.jobs_reference, market.jobs_live, market.skills, market.companies, market.sources "
                    "RESTART IDENTITY")
        _copy_csv(cur, "sources", sources)
        _copy_csv(cur, "companies", pd.DataFrame({"name": companies}))
        _copy_csv(cur, "skills", skills)
        # Surrogate keys are generated by PostgreSQL: read them back instead of
        # assuming an order (insertion/collation order is not guaranteed).
        company_id = dict(cur.execute("SELECT name, company_id FROM market.companies").fetchall())
        skill_id = dict(cur.execute("SELECT name, skill_id FROM market.skills").fetchall())
        _load_facts(cur, live, live_skills, ref, ref_skills, descriptions, company_id, skill_id)

        expected = {
            "sources": len(sources), "companies": len(companies), "skills": len(skills),
            "jobs_live": json.loads((reports / "arbeitnow.json").read_text())["processed_profile"]["rows"],
            "jobs_reference": json.loads((reports / "data_jobs.json").read_text())["processed_profile"]["rows"],
            "job_skills_live": len(live_skills), "job_skills_reference": len(ref_skills),
        }
        if descriptions is not None:
            expected["job_descriptions"] = len(descriptions)
        actual = {}
        for table in expected:
            cur.execute(f"SELECT COUNT(*) FROM market.{table}")  # table names come from the fixed dict above
            actual[table] = cur.fetchone()[0]
        if actual != expected:
            raise RuntimeError(f"Row count mismatch, rolling back: expected {expected}, got {actual}")
        cur.execute("ANALYZE")
    print(f"Loaded in {time.time() - started:.0f}s:", json.dumps(actual))
    return actual


def _load_facts(cur, live, live_skills, ref, ref_skills, descriptions, company_id, skill_id) -> None:
    live = live.assign(source_id="arbeitnow", company_id=live["company_name"].str.strip().map(company_id))
    live["tags"] = live["tags"].fillna("").map(lambda s: [t for t in s.split("|") if t])
    live["job_types_raw"] = live["job_types_raw"].fillna("").map(lambda s: [t for t in s.split("|") if t])
    live = live[LIVE_COLUMNS]

    ref = ref.rename(columns={"job_work_from_home": "work_from_home", "job_no_degree_mention": "no_degree_mention",
                              "job_health_insurance": "health_insurance"})
    ref = ref.assign(source_id="data_jobs_2023", company_id=ref["company_name"].str.strip().map(company_id),
                     posted_month=ref["posted_month"] + "-01")
    ref = _int_columns(ref, ["company_id", "skill_count", *[f"{t}_skill_count" for t in REF_SKILL_TYPES]])[REF_COLUMNS]

    live_links = live_skills.assign(skill_id=live_skills["skill"].map(skill_id))[["job_id", "skill_id"]]
    ref_links = ref_skills.assign(skill_id=ref_skills["skill"].map(skill_id))[["job_id", "skill_id", "skill_type", "skill_raw"]]

    _copy_rows(cur, "jobs_live", live)
    if descriptions is not None:
        _copy_csv(cur, "job_descriptions", descriptions.rename(
            columns={"description_language": "language", "description_text": "body"})[["job_id", "language", "body"]])
    _copy_csv(cur, "jobs_reference", ref)
    _copy_csv(cur, "job_skills_live", live_links)
    _copy_csv(cur, "job_skills_reference", ref_links)


if __name__ == "__main__":
    load()
