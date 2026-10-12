"""PostgreSQL integration tests (real server, synthetic data).

A throw-away PostgreSQL cluster is created with `initdb` in a temporary
directory, then the real `market.db.setup` and `market.db.load` code run
against it. Skipped automatically when PostgreSQL server binaries are absent.
"""

from __future__ import annotations

import glob
import json
import os
import secrets
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
import pytest

psycopg = pytest.importorskip("psycopg")

from market.cleaning_arbeitnow import clean_arbeitnow  # noqa: E402
from market.cleaning_data_jobs import clean_data_jobs  # noqa: E402
from market.db import load as db_load  # noqa: E402
from market.db import queries, run_queries, setup as db_setup  # noqa: E402
from market.pipeline import build_skill_vocabulary  # noqa: E402
from tests.test_market import job  # noqa: E402

PG_BINS = sorted(glob.glob("/usr/lib/postgresql/*/bin"))
pytestmark = pytest.mark.skipif(not PG_BINS or not shutil.which("runuser") and os.geteuid() == 0,
                                reason="PostgreSQL server binaries not available")

DATA_JOBS_HEADER = (
    "job_title_short,job_title,job_location,job_via,job_schedule_type,job_work_from_home,search_location,"
    "job_posted_date,job_no_degree_mention,job_health_insurance,job_country,salary_rate,salary_year_avg,"
    "salary_hour_avg,company_name,job_skills,job_type_skills")
DATA_JOBS_ROWS = [
    'Senior Data Engineer,Senior Data Engineer,"Austin, TX",via LinkedIn,Full-time,False,Sudan,2023-03-01 10:00:00,False,True,Sudan,year,150000,,ACME GmbH,"[\'python\', \'aws\']","{\'programming\': [\'python\'], \'cloud\': [\'aws\']}"',
    'Data Engineer,Data Engineer,"Berlin, Germany",via Indeed,Full-time,True,Germany,2023-04-02 10:00:00,True,False,Germany,,,,Beta,"[\'sql\', \'python\', \'hadoop\']","{\'programming\': [\'sql\', \'python\'], \'libraries\': [\'hadoop\']}"',
    'Data Analyst,Data Analyst,"Paris, France",via Indeed,,False,France,2023-05-02 10:00:00,False,False,France,,,,Gamma,,',
]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _as_pg(cmd: list[str]) -> list[str]:
    return ["runuser", "-u", "postgres", "--", *cmd] if os.geteuid() == 0 else cmd


@pytest.fixture(scope="module")
def pg_server():
    bindir = PG_BINS[-1]
    datadir = tempfile.mkdtemp(prefix="coach-pg-")
    port = _free_port()
    admin_password = secrets.token_urlsafe(12)
    pwfile = Path(datadir + ".pw")
    pwfile.write_text(admin_password)
    if os.geteuid() == 0:
        shutil.chown(datadir, "postgres", "postgres")
        shutil.chown(pwfile, "postgres")
    subprocess.run(_as_pg([f"{bindir}/initdb", "-D", datadir, "-U", "postgres", f"--pwfile={pwfile}",
                           "--auth=scram-sha-256", "--encoding=UTF8"]), check=True, capture_output=True)
    pwfile.unlink()
    subprocess.run(_as_pg([f"{bindir}/pg_ctl", "-D", datadir, "-w", "-l", f"{datadir}/log",
                           "-o", f"-p {port} -c listen_addresses=127.0.0.1 -k {datadir}", "start"]),
                   check=True, capture_output=True)
    env = {
        "DATABASE_ADMIN_URL": f"postgresql://postgres:{admin_password}@127.0.0.1:{port}/postgres",
        "COACH_OWNER_PASSWORD": secrets.token_urlsafe(12),
        "COACH_READER_PASSWORD": secrets.token_urlsafe(12),
    }
    env["DATABASE_OWNER_URL"] = f"postgresql://coach_owner:{env['COACH_OWNER_PASSWORD']}@127.0.0.1:{port}/job_market"
    env["DATABASE_URL"] = f"postgresql://coach_reader:{env['COACH_READER_PASSWORD']}@127.0.0.1:{port}/job_market"
    previous = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        db_setup.setup()
        yield env
    finally:
        for k, v in previous.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        subprocess.run(_as_pg([f"{bindir}/pg_ctl", "-D", datadir, "-w", "-m", "immediate", "stop"]), capture_output=True)
        shutil.rmtree(datadir, ignore_errors=True)


@pytest.fixture(scope="module")
def processed(tmp_path_factory) -> tuple[Path, Path]:
    """Tiny processed dataset with the exact Phase-2 layout."""
    root = tmp_path_factory.mktemp("data")
    processed_dir, raw_dir = root / "processed", root / "raw"
    for d in (processed_dir / "arbeitnow", processed_dir / "data_jobs", processed_dir / "reports", raw_dir / "hf_data_jobs"):
        d.mkdir(parents=True)

    raw_live = [job("a"), job("b", title="Senior Data Scientist", tags=["AI"], remote=True,
                              desc="<p>You will build machine learning models with Python, SQL and AWS for our platform.</p>"),
                job("c", title="Account Executive", company_name="Beta", tags=["Sales"], job_types=[],
                    desc="<p>Sales role with CRM and Excel, communication skills.</p>")]
    live, live_skills, descriptions, _ = clean_arbeitnow(raw_live, "snap-test")
    live.to_csv(processed_dir / "arbeitnow" / "jobs.csv", index=False)
    live_skills.to_csv(processed_dir / "arbeitnow" / "job_skills.csv", index=False)
    descriptions.to_csv(processed_dir / "arbeitnow" / "descriptions.csv.gz", index=False)

    csv = root / "data_jobs.csv"
    csv.write_text("\n".join([DATA_JOBS_HEADER, *DATA_JOBS_ROWS]) + "\n")
    ref, ref_skills, _ = clean_data_jobs(csv)
    ref.to_csv(processed_dir / "data_jobs" / "jobs.csv.gz", index=False)
    ref_skills.to_csv(processed_dir / "data_jobs" / "job_skills.csv.gz", index=False)

    build_skill_vocabulary({"arbeitnow": (live, live_skills), "data_jobs": (ref[~ref.skills_missing], ref_skills)}) \
        .to_csv(processed_dir / "skills.csv", index=False)
    (processed_dir / "reports" / "arbeitnow.json").write_text(json.dumps({
        "snapshot": "snap-test", "manifest": {"url": "https://example.test/api", "started_at_utc": "2026-10-08T00:00:00+00:00"},
        "raw_profile": {"rows": len(raw_live)}, "processed_profile": {"rows": len(live)}}))
    (processed_dir / "reports" / "data_jobs.json").write_text(json.dumps({
        "raw_profile": {"rows": len(DATA_JOBS_ROWS)}, "processed_profile": {"rows": len(ref)}}))
    (raw_dir / "hf_data_jobs" / "manifest.json").write_text(json.dumps({
        "source": "https://example.test/dataset", "license": "Apache-2.0", "revision": "abc",
        "downloaded_at_utc": "2026-10-08T00:00:00+00:00"}))
    return processed_dir, raw_dir


@pytest.fixture(scope="module")
def loaded(pg_server, processed):
    return db_load.load(*processed)


def reader():
    return psycopg.connect(os.environ["DATABASE_URL"])


def owner():
    return psycopg.connect(os.environ["DATABASE_OWNER_URL"])


def test_load_counts_match_inputs(loaded, processed):
    processed_dir, _ = processed
    assert loaded["jobs_live"] == 3 and loaded["jobs_reference"] == 3
    assert loaded["job_skills_live"] == len(pd.read_csv(processed_dir / "arbeitnow" / "job_skills.csv"))
    assert loaded["job_skills_reference"] == 5  # python+aws, sql+python+hadoop
    assert loaded["companies"] == 3 and loaded["sources"] == 2 and loaded["job_descriptions"] == 3


def test_load_is_idempotent(loaded, processed):
    assert db_load.load(*processed) == loaded


def test_load_rolls_back_on_count_mismatch(loaded, processed):
    processed_dir, raw_dir = processed
    report = processed_dir / "reports" / "arbeitnow.json"
    original = report.read_text()
    tampered = json.loads(original)
    tampered["raw_profile"]["rows"] = tampered["processed_profile"]["rows"] = 99  # consistent, but wrong
    report.write_text(json.dumps(tampered))
    try:
        with pytest.raises(RuntimeError, match="Row count mismatch"):
            db_load.load(processed_dir, raw_dir)
    finally:
        report.write_text(original)
    with reader() as conn:  # previous content still there
        assert conn.execute("SELECT COUNT(*) FROM market.jobs_live").fetchone()[0] == 3


def test_reader_is_read_only_and_cannot_see_descriptions(loaded):
    with reader() as conn:
        assert conn.execute("SELECT COUNT(*) FROM market.v_live_family_summary").fetchone()[0] >= 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SELECT body FROM market.job_descriptions")
    with reader() as conn:
        with pytest.raises((psycopg.errors.ReadOnlySqlTransaction, psycopg.errors.InsufficientPrivilege)):
            conn.execute("DELETE FROM market.skills")
    with owner() as conn:
        assert conn.execute("SELECT COUNT(*) FROM market.job_descriptions").fetchone()[0] == 3


def test_constraints_reject_invalid_rows(loaded):
    with owner() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute("UPDATE market.jobs_live SET experience_level = 'wizard' WHERE slug = 'a'")
    with owner() as conn:
        with pytest.raises(psycopg.errors.CheckViolation):  # skill counts must be NULL iff skills are missing
            conn.execute("UPDATE market.jobs_reference SET skill_count = NULL WHERE NOT skills_missing")
    with owner() as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("INSERT INTO market.job_skills_live VALUES ('arbeitnow:nope', 1)")


def test_country_repair_and_missing_skills_survive_loading(loaded):
    with reader() as conn:
        rows = dict(conn.execute("SELECT job_location, country FROM market.jobs_reference").fetchall())
        assert rows["Austin, TX"] == "United States"
        assert conn.execute("SELECT skill_count FROM market.jobs_reference WHERE skills_missing").fetchone() == (None,)


def test_skill_demand_is_parameterised_and_per_source(loaded):
    with reader() as conn:
        demand = {d["skill"]: d for d in queries.skill_demand(conn, ["Python", "AWS", "Kubernetes"], "Data Engineer")}
        assert demand["Python"]["reference_share_pct"] == 100.0   # 2 of 2 data engineer postings
        assert demand["AWS"]["reference_share_pct"] == 50.0
        assert demand["Kubernetes"]["reference_postings"] == 0
        assert demand["Python"]["live_tech_postings"] >= 1
        # Hostile input is just an unknown skill name, never SQL.
        hostile = queries.skill_demand(conn, ["x'); DROP TABLE market.skills; --"])
        assert hostile[0]["reference_postings"] == 0
        assert conn.execute("SELECT COUNT(*) FROM market.skills").fetchone()[0] > 0
        assert queries.role_families(conn) == ["Data Analyst", "Data Engineer"]


def test_all_analysis_queries_run(loaded, tmp_path):
    parsed = run_queries.parse_queries(run_queries.SQL_FILE.read_text())
    assert len(parsed) == 15 and all(q["question"] for q in parsed)
    summary = run_queries.run_all(out_dir=tmp_path)
    assert {s["name"] for s in summary} == {q["name"] for q in parsed}
    counts = pd.read_csv(tmp_path / "01_table_row_counts.csv").set_index("table_name")["row_count"]
    assert counts["jobs_live"] == 3 and counts["jobs_reference"] == 3
    checks = pd.read_csv(tmp_path / "15_data_quality_checks.csv").set_index("check_name")["value"]
    assert checks["live postings whose skill_count differs from job_skills rows"] == 0
