"""Ingestion of the public Arbeitnow Job Board API (live JSON source).

API:   https://www.arbeitnow.com/api/job-board-api  (free, public, no key)
Terms: "free public API for jobs, please do not abuse ... linking back
       appreciated ... by using the API you agree to the terms of service on
       Arbeitnow.com". robots.txt allows all paths. Responses advertise
       `x-ratelimit-limit: 50`.

Design decisions:
- Raw responses are written to disk *unchanged* (one JSON file per page) in a
  dated snapshot folder, with a manifest. Cleaning never edits raw files, so
  every processed number can be recomputed from the snapshot.
- Politeness: one request every `delay` seconds (default 2 s, i.e. 30/min,
  below the advertised limit), a hard page cap, an identifying User-Agent and
  retry with backoff only on 429/5xx.
- Every job is validated with Pydantic before it is accepted, so a schema
  change on the provider side is detected instead of silently producing
  empty columns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic import BaseModel, ValidationError

from market import RAW_DIR

API_URL = "https://www.arbeitnow.com/api/job-board-api"
USER_AGENT = "ai-job-interview-coach/1.0 (bootcamp research project; respectful polling)"


class ArbeitnowJob(BaseModel):
    """Schema of one job as returned by the API (checked on 2026-10-08)."""

    slug: str
    company_name: str
    title: str
    description: str
    remote: bool
    url: str
    tags: list[str]
    job_types: list[str]
    location: str
    created_at: int  # Unix timestamp (seconds)


class PageValidation(BaseModel):
    page: int
    jobs: int
    valid: int
    invalid: int
    errors: list[str]


def validate_page(payload: dict, page: int) -> PageValidation:
    jobs = payload.get("data")
    if not isinstance(jobs, list):
        raise ValueError(f"Page {page}: response has no 'data' list (keys: {sorted(payload)})")
    errors: list[str] = []
    valid = 0
    for i, job in enumerate(jobs):
        try:
            ArbeitnowJob.model_validate(job)
            valid += 1
        except ValidationError as exc:
            errors.append(f"job {i}: " + "; ".join(f"{'.'.join(map(str, e['loc']))} {e['msg']}" for e in exc.errors()))
    return PageValidation(page=page, jobs=len(jobs), valid=valid, invalid=len(jobs) - valid, errors=errors[:20])


def _get(client: httpx.Client, page: int, retries: int = 3) -> dict:
    for attempt in range(retries + 1):
        response = client.get(API_URL, params={"page": page})
        if response.status_code == 200:
            return response.json()
        if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            time.sleep(10 * (attempt + 1))  # back off generously; we are not in a hurry
            continue
        response.raise_for_status()
    raise RuntimeError("unreachable")  # pragma: no cover


def fetch_snapshot(out_root: Path = RAW_DIR / "arbeitnow", max_pages: int = 60, delay: float = 2.0,
                   client: httpx.Client | None = None) -> Path:
    """Download all pages (up to `max_pages`) into a new timestamped snapshot folder."""
    started = datetime.now(timezone.utc)
    folder = out_root / started.strftime("%Y%m%dT%H%M%SZ")
    folder.mkdir(parents=True, exist_ok=False)
    own_client = client is None
    client = client or httpx.Client(headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=30)
    pages: list[dict] = []
    stop_reason = f"reached max_pages={max_pages}"
    try:
        for page in range(1, max_pages + 1):
            payload = _get(client, page)
            raw = json.dumps(payload, ensure_ascii=False)
            (folder / f"page_{page:03d}.json").write_text(raw, encoding="utf-8")
            check = validate_page(payload, page)
            pages.append({**check.model_dump(), "sha256": hashlib.sha256(raw.encode()).hexdigest()})
            print(f"page {page}: {check.jobs} jobs ({check.invalid} invalid)")
            if check.jobs == 0:
                stop_reason = "empty page"
                break
            if not (payload.get("links") or {}).get("next"):
                stop_reason = "no next link (last page)"
                break
            time.sleep(delay)
    finally:
        if own_client:
            client.close()
    manifest = {
        "source": "Arbeitnow Job Board API",
        "url": API_URL,
        "terms": "Free public API; do not abuse; link back to arbeitnow.com; Arbeitnow terms of service apply.",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "request_delay_seconds": delay,
        "stop_reason": stop_reason,
        "pages": pages,
        "total_jobs": sum(p["jobs"] for p in pages),
        "total_invalid": sum(p["invalid"] for p in pages),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return folder


def load_snapshot(folder: Path) -> list[dict]:
    """Read every job of a snapshot (raw dicts, in page order)."""
    jobs: list[dict] = []
    for path in sorted(folder.glob("page_*.json")):
        jobs.extend(json.loads(path.read_text(encoding="utf-8"))["data"])
    return jobs


def latest_snapshot(root: Path = RAW_DIR / "arbeitnow") -> Path:
    folders = sorted(p for p in root.iterdir() if p.is_dir() and (p / "manifest.json").exists())
    if not folders:
        raise FileNotFoundError(f"No Arbeitnow snapshot in {root}. Run: python -m market.ingestion.arbeitnow")
    return folders[-1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download a polite snapshot of the Arbeitnow job API.")
    parser.add_argument("--max-pages", type=int, default=60)
    parser.add_argument("--delay", type=float, default=2.0)
    args = parser.parse_args()
    out = fetch_snapshot(max_pages=args.max_pages, delay=args.delay)
    print("Snapshot written to", out)
