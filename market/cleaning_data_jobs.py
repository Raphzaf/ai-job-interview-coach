"""Cleaning + feature engineering for the reference dataset lukebarousse/data_jobs.

Input:  data/raw/hf_data_jobs/data_jobs.csv (785k rows, 2023, Apache-2.0)
Output: jobs + job_skills tables (same layout idea as the Arbeitnow tables, but
        kept as a separate source: different years, collection methods and
        skill extraction, so the two are never merged into one fact table).
"""

from __future__ import annotations

import ast
import re

import numpy as np
import pandas as pd

from app.matching.skills import normalize_skill
from market.cleaning_arbeitnow import CleaningReport

US_STATE = re.compile(r",\s*[A-Z]{2}$")
US_STATE_NAMES = {"Texas", "California", "New York", "Florida", "Georgia", "Illinois", "Ohio", "Arizona",
                  "Colorado", "Washington", "Virginia", "New Mexico", "Oklahoma", "Massachusetts"}
_TITLE_SENIOR = re.compile(r"\b(?:senior|sr\.?|lead|principal|staff|head)\b", re.IGNORECASE)
_TITLE_JUNIOR = re.compile(r"\b(?:junior|jr\.?|entry[\s-]level|graduate|associate|intern)\b", re.IGNORECASE)

SCHEDULE_ORDER = ["Full-time", "Part-time", "Contractor", "Internship", "Temp work", "Per diem", "Volunteer"]

# Skill-type keys used by the source (job_type_skills) -> feature names.
SKILL_TYPES = ["programming", "cloud", "libraries", "databases", "analyst_tools", "other", "os",
               "webframeworks", "async", "sync"]


def parse_literal(value):
    """Parse the Python-literal strings used by the source ("['sql', 'python']")."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return None


def canonical_skill(raw: str) -> tuple[str, bool]:
    """Map a source skill to the coach taxonomy when possible (shared vocabulary)."""
    canon = normalize_skill(raw)
    return (canon, True) if canon else (raw.strip().lower(), False)


def fix_country(row_country: str, location: str, search_location: str) -> tuple[str | None, bool]:
    """Repair the country field where it is a search artefact.

    Measured: all 21,781 rows labelled 'Sudan' have search_location 'Sudan' and
    none has a Sudanese location; 20,865 are US-style or 'Anywhere' locations.
    The country therefore came from the bot's search parameter, not the posting.
    """
    if row_country != "Sudan" or "Sudan" in str(location):
        return row_country, False
    loc = str(location).strip()
    if US_STATE.search(loc) or loc == "United States" or loc in US_STATE_NAMES:
        return "United States", True
    return None, True  # 'Anywhere' and others: unknown


def schedule_primary(value) -> str:
    if not isinstance(value, str) or not value.strip():
        return "Unknown"
    for label in SCHEDULE_ORDER:
        if value.startswith(label) or value.lower().startswith(label.lower()):
            return label
    return "Other"


def clean_data_jobs(csv_path) -> tuple[pd.DataFrame, pd.DataFrame, CleaningReport]:
    report = CleaningReport()
    df = pd.read_csv(csv_path)
    n0 = len(df)
    report.add("load", n0, n0, f"{n0} rows x {df.shape[1]} columns")

    df = df.drop_duplicates()
    report.add("drop exact duplicate rows", n0, len(df), "all 17 columns identical")

    n = len(df)
    df = df.drop_duplicates(subset=["job_title", "company_name", "job_location", "job_posted_date"])
    report.add("drop duplicate postings", n, len(df),
               "same title, company, location and posting timestamp (scraped twice with different metadata)")

    # Types and strings.
    df["posted_at"] = pd.to_datetime(df["job_posted_date"], errors="coerce")
    n = len(df)
    df = df[df["posted_at"].notna()]
    report.add("drop unparseable dates", n, len(df), "job_posted_date not a valid timestamp")
    df["posted_month"] = df["posted_at"].dt.to_period("M").astype(str)
    df["job_via"] = df["job_via"].str.replace(r"^via\s+", "", regex=True).str.strip()
    for col in ["job_work_from_home", "job_no_degree_mention", "job_health_insurance"]:
        df[col] = df[col].astype(bool)
    df["schedule"] = df["job_schedule_type"].map(schedule_primary)

    fixed = [fix_country(c, l, s) for c, l, s in zip(df["job_country"], df["job_location"], df["search_location"])]
    df["country"] = [c for c, _ in fixed]
    df["country_repaired"] = [r for _, r in fixed]

    # Target-like labels. job_title_short was produced by the dataset author's
    # BERT title classifier, so it must never be paired with title text as a feature.
    df["is_senior"] = df["job_title_short"].str.startswith("Senior ")
    df["role_family"] = df["job_title_short"].str.replace(r"^Senior ", "", regex=True)
    df["title_seniority"] = np.select(
        [df["job_title"].str.contains(_TITLE_SENIOR, na=False), df["job_title"].str.contains(_TITLE_JUNIOR, na=False)],
        ["senior", "junior"], default="unspecified")

    # Skills: parse the literal lists; missing lists stay missing (NOT zero
    # skills) because 14.9% of rows simply had no extraction.
    skills = df["job_skills"].map(parse_literal)
    types = df["job_type_skills"].map(parse_literal)
    df["skills_missing"] = skills.isna()
    df["skill_count"] = skills.map(lambda s: len(s) if isinstance(s, list) else np.nan)
    for t in SKILL_TYPES:
        df[f"{t}_skill_count"] = np.where(df["skills_missing"], np.nan,
                                          types.map(lambda d, t=t: len(d.get(t, [])) if isinstance(d, dict) else 0))

    # Salary: annual average only (hourly rates are not comparable without hours).
    df["has_salary"] = df["salary_year_avg"].notna()
    df["log_salary_year"] = np.log(df["salary_year_avg"])

    df = df.reset_index(drop=True)
    df.insert(0, "job_id", "data_jobs:" + df.index.astype(str))
    df["source"] = "data_jobs_2023"

    # job_skills long table with source skill type + canonical name.
    rows = []
    for job_id, d in zip(df["job_id"], types):
        if isinstance(d, dict):
            for skill_type, names in d.items():
                for name in names:
                    canon, mapped = canonical_skill(name)
                    rows.append((job_id, canon, name, skill_type, mapped))
    job_skills = pd.DataFrame(rows, columns=["job_id", "skill", "skill_raw", "skill_type", "in_coach_taxonomy"])
    job_skills = job_skills.drop_duplicates(["job_id", "skill"])

    jobs = df[[
        "job_id", "source", "job_title", "job_title_short", "role_family", "is_senior", "title_seniority",
        "company_name", "job_location", "country", "country_repaired", "search_location", "job_via", "schedule",
        "job_work_from_home", "job_no_degree_mention", "job_health_insurance", "posted_at", "posted_month",
        "salary_rate", "salary_year_avg", "salary_hour_avg", "has_salary", "log_salary_year", "skills_missing",
        "skill_count", *[f"{t}_skill_count" for t in SKILL_TYPES],
    ]].copy()
    return jobs, job_skills, report
