"""Download of the reference dataset `lukebarousse/data_jobs` (Hugging Face).

Real data-job postings from 2023, collected by Luke Barousse from Google Jobs
search results (via SerpApi) and published under the Apache-2.0 license:
https://huggingface.co/datasets/lukebarousse/data_jobs

Reproducibility: the download is pinned to an exact dataset commit and checked
against the SHA-256 published by Hugging Face (Git LFS object id). The file is
231 MB, so it lives in data/raw/hf_data_jobs/ which is git-ignored.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx

from market import RAW_DIR

REPO = "lukebarousse/data_jobs"
REVISION = "ed776e5a0a8c40ea9d5efbd800772ae52e140f3e"  # dataset commit checked on 2026-10-08
FILENAME = "data_jobs.csv"
EXPECTED_SHA256 = "635241ed09ccee18bdae1f83b45f26d6759e0aa2513c529f6190e9054062436c"
EXPECTED_BYTES = 231_152_089
URL = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{FILENAME}"
TARGET_DIR = RAW_DIR / "hf_data_jobs"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(target_dir: Path = TARGET_DIR, force: bool = False) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / FILENAME
    if target.exists() and not force and sha256_of(target) == EXPECTED_SHA256:
        print("Already downloaded and verified:", target)
        return target
    tmp = target.with_suffix(".part")
    with httpx.stream("GET", URL, follow_redirects=True, timeout=120) as response:
        response.raise_for_status()
        with tmp.open("wb") as handle:
            for chunk in response.iter_bytes(1 << 20):
                handle.write(chunk)
    actual = sha256_of(tmp)
    if actual != EXPECTED_SHA256:
        tmp.unlink()
        raise RuntimeError(f"Checksum mismatch for {FILENAME}: {actual} != {EXPECTED_SHA256}")
    tmp.rename(target)
    (target_dir / "manifest.json").write_text(json.dumps({
        "source": f"https://huggingface.co/datasets/{REPO}",
        "revision": REVISION,
        "file": FILENAME,
        "bytes": target.stat().st_size,
        "sha256": actual,
        "license": "Apache-2.0",
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2), encoding="utf-8")
    print("Downloaded and verified:", target)
    return target


if __name__ == "__main__":
    download()
