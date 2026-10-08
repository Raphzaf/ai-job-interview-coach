# Data folder

| Path | Content | In Git? |
|---|---|---|
| `examples/` | Fictional CV and job description for the interview-coach demo | ✅ |
| `raw/arbeitnow/<snapshot>/manifest.json` | Arbeitnow API snapshot metadata: time, stop reason, per-page SHA-256 | ✅ |
| `raw/arbeitnow/<snapshot>/page_*.json` | Unmodified API responses (full job descriptions, some with contact details) | ❌ local only |
| `raw/hf_data_jobs/manifest.json` | Pinned dataset revision, SHA-256, license | ✅ |
| `raw/hf_data_jobs/data_jobs.csv` | `lukebarousse/data_jobs` (Apache-2.0), 231 MB | ❌ download with `python -m market.ingestion.hf_data_jobs` |
| `processed/arbeitnow/jobs.csv`, `job_skills.csv` | Cleaned postings + features, **no free text** | ✅ |
| `processed/arbeitnow/descriptions.csv.gz` | Cleaned description text | ❌ local only |
| `processed/data_jobs/` | Cleaned 2023 reference tables (≈ 52 MB) | ❌ regenerate with `python -m market.pipeline` |
| `processed/skills.csv` | Shared skill vocabulary with per-source demand | ✅ |
| `processed/reports/*.json` | Profiling + cleaning reports (source of every number in the docs) | ✅ |

Attribution: job postings in `processed/arbeitnow/` come from the [Arbeitnow](https://www.arbeitnow.com) job board API; each row keeps its original `url`. The reference dataset is [lukebarousse/data_jobs](https://huggingface.co/datasets/lukebarousse/data_jobs) by Luke Barousse (Apache-2.0).

See [`docs/DATA_PIPELINE.md`](../docs/DATA_PIPELINE.md) for the methodology.
