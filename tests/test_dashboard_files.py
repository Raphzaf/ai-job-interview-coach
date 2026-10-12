"""The Tableau files shipped in dashboard/tableau/data: shared filters and documented numbers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

DATA = Path(__file__).resolve().parents[1] / "dashboard" / "tableau" / "data"
EXPECTED = (DATA.parent / "EXPECTED_VALUES.md").read_text(encoding="utf-8")

# A Tableau filter applied to "All Using Related Data Sources" matches values by
# name: a field shared by two files must hold the same values in both.
SHARED = [
    ("ref_overview_2023", "ref_skill_demand_2023", ["role_family", "seniority", "country_group", "remote"]),
    ("live_jobs_2026", "live_skill_demand_2026", ["job_family", "experience_level", "remote", "description_language"]),
]


@pytest.fixture(scope="module")
def files():
    return {p.stem: pd.read_csv(p) for p in DATA.glob("*.csv")}


@pytest.mark.parametrize(("a", "b", "cols"), SHARED)
def test_shared_filter_fields_have_identical_values(files, a, b, cols):
    for col in cols:
        assert set(files[a][col].astype(str)) == set(files[b][col].astype(str)), col


def test_remote_uses_the_same_labels_everywhere(files):
    for name in ("ref_overview_2023", "ref_skill_demand_2023", "live_jobs_2026", "live_skill_demand_2026"):
        assert set(files[name]["remote"]) == {"Remote", "On-site / hybrid"}, name


def test_documented_expected_values_match_the_files(files):
    ov, lj = files["ref_overview_2023"], files["live_jobs_2026"]
    remote_2023 = 100 * ov[ov.remote == "Remote"].postings.sum() / ov.postings.sum()
    remote_2026 = 100 * (lj.remote == "Remote").mean()
    assert f"Postings **{int(ov.postings.sum()):,}** · Remote **{remote_2023:.1f} %**" in EXPECTED
    assert f"postings **{len(lj):,}**, remote **{remote_2026:.1f} %**" in EXPECTED
