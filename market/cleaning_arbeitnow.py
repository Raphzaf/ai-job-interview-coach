"""Cleaning + feature engineering for the Arbeitnow API snapshot (pandas/NumPy).

Input:  raw job dicts from data/raw/arbeitnow/<snapshot>/page_*.json
Output: three tidy tables ready for PostgreSQL (Phase 3)
        - jobs        : one row per unique posting, features, NO free text
        - job_skills  : one row per (job, skill)  [many-to-many]
        - descriptions: job_id + cleaned text (kept local: may contain
                        recruiters' phone numbers, so it is never committed)
and a cleaning report whose numbers are all computed here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.matching.skills import extract_skills, skill_category
from market.text import detect_language, html_to_text

# --- controlled vocabularies (built from the values observed in the snapshot) ---

# Ordered from least to most senior: when a posting lists several levels we
# keep the most senior one and record that the label was ambiguous.
EXPERIENCE_LEVELS = ["student_intern", "entry", "mid", "experienced", "lead_manager"]
_EXPERIENCE_MAP = {
    "student_intern": ["working student", "student", "intern", "internship", "werkstudent", "praktikum",
                       "apprenticeship", "trainee", "traineeship", "dual studies", "hilfstätigkeit / student",
                       "no experience required / student", "student college", "student (college)",
                       "student (high school)", "working student (part time)"],
    "entry": ["entry", "berufseinstieg", "principiante", "débutant", "associate"],
    "mid": ["mid", "mid-senior"],
    "experienced": ["experienced", "berufserfahren", "professional / experienced", "experienced professional",
                    "profesional / con experiencia"],
    "lead_manager": ["teamleitung", "manager", "senior manager", "executive", "geschäftsleitung"],
}
_LEVEL_OF = {v: level for level, values in _EXPERIENCE_MAP.items() for v in values}

_SCHEDULE_PATTERNS = {  # checked in this order
    "full_or_part_time": r"full or part time",
    "part_time": r"part[\s-]?time|teilzeit|minijob|nebentätigkeit|side",
    "full_time": r"full[\s-]?time|vollzeit",
}
_CONTRACT_PATTERNS = {
    "freelance": r"freelance|contractor|self-employed|freiberufler|partita iva|autónomo|auto-entrepreneur|interim|independent|consultant|^contract$|temporary/contract",
    "fixed_term": r"fixed[\s-]?term|temporary|temporär|befristet\b",
    "permanent": r"permanent|unbefristet",
}

_TITLE_SENIOR = re.compile(r"\b(senior|sr\.?|lead|principal|head of|staff|chief)\b", re.IGNORECASE)
_TITLE_JUNIOR = re.compile(r"\b(junior|jr\.?|entry[\s-]level|graduate|trainee|werkstudent|working student|intern|praktikant|praktikum|azubi|ausbildung)\b", re.IGNORECASE)

# Job family from title + tags. Order matters: the first matching family wins,
# so specific families (Data & AI) are tested before broader ones (Software & IT).
JOB_FAMILIES: list[tuple[str, str]] = [
    ("Data & AI", r"\bdata\b|machine learning|\bml\b|\bai\b|künstliche intelligenz|analytics|scientist|\bbi\b|business intelligence"),
    ("Software & IT", r"software|developer|entwickler|engineer.*(backend|frontend|full[\s-]?stack|platform|devops|cloud|software)|devops|\bit\b|informatik|system administrator|cloud|cyber|security engineer|qa\b|tester|web|frontend|backend|full[\s-]?stack|sap|android|\bios\b|mobile|tech lead|architect"),
    ("Engineering & Technical", r"engineer|ingenieur|technician|techniker|mechanical|electrical|elektro|mechatron|construction|bau"),
    ("Sales & Business Development", r"sales|vertrieb|account (executive|manager)|business development|key account"),
    ("Marketing & Communication", r"marketing|communication|kommunikation|social media|content|brand|seo|pr\b"),
    ("Finance & Accounting", r"finance|financial|accounting|accountant|buchhalt|controlling|controller|tax|steuer|audit"),
    ("HR & Recruiting", r"\bhr\b|human resources|recruit|talent|personal"),
    ("Operations & Logistics", r"operations|logistic|supply chain|procurement|einkauf|warehouse|lager"),
    ("Customer Service", r"customer (service|support|success)|kundenservice|kundenbetreuung"),
    ("Management & Consulting", r"consult|berater|manager|management|director|leitung|leiter|head"),
]
_FAMILY_RES = [(name, re.compile(rx, re.IGNORECASE)) for name, rx in JOB_FAMILIES]

CITY_ALIASES = {"münchen": "Munich", "frankfurt am main": "Frankfurt", "köln": "Cologne", "nürnberg": "Nuremberg",
                "düsseldorf": "Düsseldorf", "wien": "Vienna", "zürich": "Zurich"}

NON_TECH_CATEGORIES = {"Soft skills", "Languages", "Marketing", "Methods"}


@dataclass
class CleaningReport:
    steps: list[dict] = field(default_factory=list)

    def add(self, step: str, rows_before: int, rows_after: int, note: str) -> None:
        self.steps.append({"step": step, "rows_before": rows_before, "rows_after": rows_after,
                           "rows_removed": rows_before - rows_after, "note": note})


def _first_match(values: list[str], patterns: dict[str, str]) -> str | None:
    joined = [v.lower().strip() for v in values]
    for label, rx in patterns.items():
        if any(re.search(rx, v) for v in joined):
            return label
    return None


def experience_from_job_types(values: list[str]) -> tuple[str | None, bool]:
    levels = {_LEVEL_OF[v.lower().strip()] for v in values if v.lower().strip() in _LEVEL_OF}
    if not levels:
        return None, False
    ordered = sorted(levels, key=EXPERIENCE_LEVELS.index)
    return ordered[-1], len(levels) > 1


def seniority_from_title(title: str) -> str:
    if _TITLE_SENIOR.search(title):
        return "senior"
    if _TITLE_JUNIOR.search(title):
        return "junior"
    return "unspecified"


def job_family(title: str, tags: list[str]) -> str:
    # Title first: it is written for this job; tags are broader and noisier.
    for source in (title, " ".join(tags)):
        for name, rx in _FAMILY_RES:
            if rx.search(source):
                return name
    return "Other"


def normalize_city(location: str) -> str | None:
    loc = (location or "").strip()
    if not loc:
        return None
    first = loc.split(",")[0].strip()
    return CITY_ALIASES.get(first.lower(), first)


def clean_arbeitnow(raw_jobs: list[dict], snapshot_id: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, CleaningReport]:
    report = CleaningReport()
    df = pd.DataFrame(raw_jobs)
    df["fetch_order"] = np.arange(len(df))
    n0 = len(df)
    report.add("load", n0, n0, f"{n0} job records from {snapshot_id}")

    # 1. Exact duplicate records (same posting returned on two pages because
    #    new jobs were inserted at the top while we paginated).
    key_cols = ["slug", "title", "company_name", "description", "location", "created_at", "remote", "url"]
    df = df[~df.duplicated(subset=key_cols, keep="last")]
    report.add("drop exact duplicates", n0, len(df), "identical content returned on two pages during pagination")

    # 2. Same slug, different content = the posting was edited between page
    #    requests. Keep the most recently fetched version.
    n = len(df)
    df = df.sort_values("fetch_order").drop_duplicates("slug", keep="last")
    report.add("deduplicate by slug", n, len(df), "same posting id with edited fields: keep the last fetched version")

    # 3. Text cleaning: HTML -> plain text (keeps line structure).
    df["description_text"] = df["description"].map(html_to_text)
    n = len(df)
    df = df[df["description_text"].str.len() >= 50]
    report.add("drop empty/near-empty descriptions", n, len(df), "fewer than 50 characters after HTML removal")

    # 4. Normalisation of strings and types.
    df["title"] = df["title"].str.strip().str.replace(r"\s+", " ", regex=True)
    df["company_name"] = df["company_name"].str.strip()
    df["city"] = df["location"].map(normalize_city)
    df["location_missing"] = df["city"].isna()
    df["posted_at"] = pd.to_datetime(df["created_at"], unit="s", utc=True)
    df["posted_date"] = df["posted_at"].dt.date
    df["posted_weekday"] = df["posted_at"].dt.day_name()

    # 5. Messy multilingual job_types -> controlled vocabularies.
    levels = df["job_types"].map(experience_from_job_types)
    df["experience_level"] = levels.map(lambda x: x[0])
    df["experience_level_ambiguous"] = levels.map(lambda x: x[1])
    df["schedule"] = df["job_types"].map(lambda v: _first_match(v, _SCHEDULE_PATTERNS))
    df["contract_type"] = df["job_types"].map(lambda v: _first_match(v, _CONTRACT_PATTERNS))
    df["seniority_from_title"] = df["title"].map(seniority_from_title)
    df["job_family"] = [job_family(t, tags) for t, tags in zip(df["title"], df["tags"])]
    df["is_tech"] = df["job_family"].isin(["Data & AI", "Software & IT"])

    # 6. Possible re-posts: same title, company and city under different slugs.
    #    Flagged, not removed: they may be genuinely separate openings.
    df["probable_repost"] = df.duplicated(subset=["title", "company_name", "city"], keep="first")

    # 7. Text-derived features.
    df["description_language"] = df["description_text"].map(detect_language)
    df["description_chars"] = df["description_text"].str.len()
    df["description_words"] = df["description_text"].str.split().map(len)
    df["skills"] = [extract_skills(f"{t}\n{d}") for t, d in zip(df["title"], df["description_text"])]
    df["skill_count"] = df["skills"].map(len)
    cats = df["skills"].map(lambda s: [skill_category(x) for x in s])
    df["tech_skill_count"] = cats.map(lambda c: sum(x not in NON_TECH_CATEGORIES for x in c))
    df["soft_skill_count"] = cats.map(lambda c: c.count("Soft skills"))
    df["programming_language_count"] = cats.map(lambda c: c.count("Programming"))
    df["cloud_devops_skill_count"] = cats.map(lambda c: c.count("Cloud") + c.count("DevOps"))
    df["ai_ml_skill_count"] = cats.map(lambda c: c.count("AI/ML"))
    df["data_skill_count"] = cats.map(lambda c: c.count("Data") + c.count("Databases"))
    df["requires_english"] = df["skills"].map(lambda s: "English" in s)
    df["requires_german"] = df["skills"].map(lambda s: "German" in s)
    df["tag_count"] = df["tags"].map(len)

    df = df.reset_index(drop=True)
    df.insert(0, "job_id", "arbeitnow:" + df["slug"])
    df["source"] = "arbeitnow"
    df["snapshot_id"] = snapshot_id

    job_skills = df[["job_id", "skills"]].explode("skills").dropna().rename(columns={"skills": "skill"})
    job_skills["skill_category"] = job_skills["skill"].map(skill_category)
    descriptions = df[["job_id", "description_language", "description_text"]]

    jobs = df[[
        "job_id", "source", "snapshot_id", "slug", "url", "title", "company_name", "location", "city",
        "location_missing", "remote", "posted_at", "posted_date", "posted_weekday", "job_family", "is_tech",
        "experience_level", "experience_level_ambiguous", "seniority_from_title", "schedule", "contract_type",
        "probable_repost", "description_language", "description_chars", "description_words", "skill_count",
        "tech_skill_count", "soft_skill_count", "programming_language_count", "cloud_devops_skill_count",
        "ai_ml_skill_count", "data_skill_count", "requires_english", "requires_german", "tag_count",
    ]].copy()
    jobs["tags"] = df["tags"].map(lambda t: "|".join(t))
    jobs["job_types_raw"] = df["job_types"].map(lambda t: "|".join(t))
    return jobs, job_skills.reset_index(drop=True), descriptions, report
