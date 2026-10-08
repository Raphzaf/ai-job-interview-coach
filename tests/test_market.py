"""Tests for the job-market data pipeline (ingestion, cleaning, features, profiling).

Fixtures are tiny synthetic records shaped like the real sources; no network.
"""

import json

import httpx
import numpy as np
import pandas as pd
import pytest

from market.cleaning_arbeitnow import (
    clean_arbeitnow, experience_from_job_types, job_family, normalize_city, seniority_from_title,
)
from market.cleaning_data_jobs import canonical_skill, clean_data_jobs, fix_country, parse_literal, schedule_primary
from market.ingestion import arbeitnow
from market.ingestion.hf_data_jobs import sha256_of
from market.pipeline import build_skill_vocabulary
from market.profiling import profile, top_counts
from market.text import detect_language, html_to_text


def job(slug, title="Python Developer (m/w/d)", desc=None, **kw):
    base = {
        "slug": slug, "company_name": "ACME GmbH", "title": title,
        "description": desc or "<p>We build APIs with <strong>Python</strong> and Docker.</p><ul><li>Great team and you will grow with us</li></ul>",
        "remote": False, "url": f"https://www.arbeitnow.com/jobs/{slug}", "tags": ["IT"], "job_types": ["Experienced"],
        "location": "Berlin", "created_at": 1_790_000_000,
    }
    return {**base, **kw}


# --- ingestion ------------------------------------------------------------------------------

def test_validate_page_flags_schema_changes():
    ok = arbeitnow.validate_page({"data": [job("a")]}, 1)
    assert ok.valid == 1 and ok.invalid == 0
    broken = arbeitnow.validate_page({"data": [{**job("b"), "remote": "maybe"}]}, 1)
    assert broken.invalid == 1 and "remote" in broken.errors[0]
    with pytest.raises(ValueError):
        arbeitnow.validate_page({"jobs": []}, 1)


def test_fetch_snapshot_paginates_and_writes_raw_files(tmp_path):
    pages = {
        "1": {"data": [job("a"), job("b")], "links": {"next": "?page=2"}},
        "2": {"data": [job("c")], "links": {"next": None}},
    }
    calls = []

    def handler(request):
        calls.append(request.url.params["page"])
        return httpx.Response(200, json=pages[request.url.params["page"]])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    folder = arbeitnow.fetch_snapshot(tmp_path, max_pages=10, delay=0, client=client)
    manifest = json.loads((folder / "manifest.json").read_text())
    assert calls == ["1", "2"]
    assert manifest["total_jobs"] == 3 and manifest["stop_reason"] == "no next link (last page)"
    assert len(manifest["pages"][0]["sha256"]) == 64
    assert [j["slug"] for j in arbeitnow.load_snapshot(folder)] == ["a", "b", "c"]
    assert arbeitnow.latest_snapshot(tmp_path) == folder


def test_fetch_snapshot_respects_page_cap(tmp_path):
    client = httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"data": [job(r.url.params["page"])], "links": {"next": "x"}})))
    folder = arbeitnow.fetch_snapshot(tmp_path, max_pages=2, delay=0, client=client)
    assert json.loads((folder / "manifest.json").read_text())["stop_reason"] == "reached max_pages=2"


def test_sha256_of(tmp_path):
    f = tmp_path / "x.csv"
    f.write_bytes(b"abc")
    assert sha256_of(f) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


# --- text helpers ---------------------------------------------------------------------------

def test_html_to_text_keeps_structure_and_entities():
    text = html_to_text("<p>Hello &amp; welcome</p><ul><li>Python</li><li>SQL</li></ul>")
    assert text.split("\n") == ["Hello & welcome", "Python", "SQL"]


def test_detect_language():
    assert detect_language("We are looking for you and the team will support you with the onboarding of our product") == "en"
    assert detect_language("Wir suchen Sie und die Kollegen mit Erfahrung für das Team bei uns und für die Zukunft") == "de"
    assert detect_language("Python SQL") == "unknown"


# --- arbeitnow normalisation ------------------------------------------------------------------

@pytest.mark.parametrize("values, expected", [
    (["Full Time", "berufserfahren"], ("experienced", False)),
    (["Entry", "Experienced"], ("experienced", True)),   # most senior kept, flagged ambiguous
    (["Werkstudent"], ("student_intern", False)),
    (["Full Time"], (None, False)),
])
def test_experience_from_job_types(values, expected):
    assert experience_from_job_types(values) == expected


def test_title_family_and_city_rules():
    assert seniority_from_title("Senior Data Engineer") == "senior"
    assert seniority_from_title("Werkstudent Marketing") == "junior"
    assert seniority_from_title("Accountant") == "unspecified"
    assert job_family("Machine Learning Engineer", []) == "Data & AI"
    assert job_family("Backend Developer (m/w/d)", []) == "Software & IT"
    assert job_family("Account Executive", ["Sales"]) == "Sales & Business Development"
    assert job_family("Kampfsport Trainer", ["Sport"]) == "Other"
    assert normalize_city("München, Bayern") == "Munich" and normalize_city("  ") is None


def test_clean_arbeitnow_dedup_features_and_report():
    raw = [
        job("a"),
        job("a"),                                            # exact duplicate (page overlap)
        job("b", title="Senior Data Scientist", tags=["AI"]),
        job("b", title="Senior Data Scientist", tags=["AI"], remote=True),  # edited version: kept
        job("c", desc="<p>x</p>"),                           # near-empty description: dropped
        job("d", title="Python Developer (m/w/d)"),          # same title/company/city as "a": repost flag
    ]
    jobs, job_skills, descriptions, report = clean_arbeitnow(raw, "snap")
    steps = {s["step"]: s["rows_removed"] for s in report.steps}
    assert steps == {"load": 0, "drop exact duplicates": 1, "deduplicate by slug": 1, "drop empty/near-empty descriptions": 1}
    assert list(jobs["slug"]) == ["a", "b", "d"]
    b = jobs.set_index("slug").loc["b"]
    assert b["remote"] and b["job_family"] == "Data & AI" and b["seniority_from_title"] == "senior"
    assert jobs.set_index("slug").loc["d", "probable_repost"]
    a = jobs.set_index("slug").loc["a"]
    assert a["skill_count"] == 2 and a["programming_language_count"] == 1 and a["description_language"] == "en"
    assert set(job_skills[job_skills.job_id == "arbeitnow:a"]["skill"]) == {"Python", "Docker"}
    assert "description_text" not in jobs.columns and len(descriptions) == 3  # free text kept out of the jobs table


# --- data_jobs normalisation ------------------------------------------------------------------

def test_parse_literal_and_canonical_skills():
    assert parse_literal("['sql', 'python']") == ["sql", "python"]
    assert parse_literal("not a list [") is None and parse_literal(np.nan) is None
    assert canonical_skill("postgresql") == ("PostgreSQL", True)
    assert canonical_skill("Hadoop") == ("hadoop", False)


@pytest.mark.parametrize("country, location, expected", [
    ("Sudan", "Dallas, TX", ("United States", True)),
    ("Sudan", "Anywhere", (None, True)),
    ("Sudan", "Khartoum, Sudan", ("Sudan", False)),
    ("Germany", "Berlin, Germany", ("Germany", False)),
])
def test_fix_country(country, location, expected):
    assert fix_country(country, location, "Sudan") == expected


def test_schedule_primary():
    assert schedule_primary("Full-time and Part-time") == "Full-time"
    assert schedule_primary(np.nan) == "Unknown"


def test_clean_data_jobs_on_fixture(tmp_path):
    header = ("job_title_short,job_title,job_location,job_via,job_schedule_type,job_work_from_home,search_location,"
              "job_posted_date,job_no_degree_mention,job_health_insurance,job_country,salary_rate,salary_year_avg,"
              "salary_hour_avg,company_name,job_skills,job_type_skills")
    rows = [
        'Senior Data Engineer,Senior Data Engineer,"Austin, TX",via LinkedIn,Full-time,False,Sudan,2023-03-01 10:00:00,False,True,Sudan,year,150000,,ACME,"[\'python\', \'aws\']","{\'programming\': [\'python\'], \'cloud\': [\'aws\']}"',
        'Data Analyst,Data Analyst,"Berlin, Germany",via Indeed,,True,Germany,2023-04-02 10:00:00,True,False,Germany,,,,Beta,,',
    ]
    rows.append(rows[1])  # exact duplicate
    path = tmp_path / "data_jobs.csv"
    path.write_text("\n".join([header, *rows]) + "\n")
    jobs, job_skills, report = clean_data_jobs(path)
    assert [s["rows_removed"] for s in report.steps] == [0, 1, 0, 0]
    senior = jobs.iloc[0]
    assert senior["is_senior"] and senior["role_family"] == "Data Engineer" and senior["country"] == "United States"
    assert senior["skill_count"] == 2 and senior["cloud_skill_count"] == 1
    assert senior["log_salary_year"] == pytest.approx(np.log(150000))
    analyst = jobs.iloc[1]
    assert analyst["skills_missing"] and np.isnan(analyst["skill_count"])  # missing, not zero
    assert analyst["schedule"] == "Unknown" and analyst["job_work_from_home"]
    assert set(job_skills["skill"]) == {"Python", "AWS"} and job_skills["in_coach_taxonomy"].all()


# --- profiling & vocabulary -----------------------------------------------------------------

def test_profile_counts_missing_and_duplicates():
    df = pd.DataFrame({"a": [1, 1, None], "b": ["x", "x", "y"], "c": [True, True, False]})
    p = profile(df, "t")
    assert p["rows"] == 3 and p["duplicate_rows"] == 1
    assert p["column_profiles"]["a"]["missing"] == 1 and p["column_profiles"]["a"]["missing_pct"] == 33.33
    assert p["column_profiles"]["c"]["true_pct"] == 66.67
    assert top_counts(df["b"])[0] == {"value": "x", "count": 2, "pct": 66.67}


def test_skill_vocabulary_shares_are_within_source():
    jobs_a = pd.DataFrame({"job_id": ["a1", "a2"]})
    skills_a = pd.DataFrame({"job_id": ["a1", "a2", "a2"], "skill": ["Python", "Python", "SQL"]})
    jobs_b = pd.DataFrame({"job_id": ["b1", "b2", "b3", "b4"]})
    skills_b = pd.DataFrame({"job_id": ["b1"], "skill": ["Python"]})
    vocab = build_skill_vocabulary({"a": (jobs_a, skills_a), "b": (jobs_b, skills_b)}).set_index("skill")
    assert vocab.loc["Python", "a_share_pct"] == 100 and vocab.loc["Python", "b_share_pct"] == 25
    assert vocab.loc["SQL", "b_postings"] == 0 and vocab.loc["SQL", "in_coach_taxonomy"]
