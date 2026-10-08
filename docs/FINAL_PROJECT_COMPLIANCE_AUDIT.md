# Final Project — Compliance Audit (Phase 1)

**Project (target):** AI Job Market & Interview Coach. From job-market data to personalised interview preparation.
**Audit date:** 2026-10-08 · **Branch:** `claude/happy-noether-mlv1hz` (PR #1) · **Audited commit:** `cd4eaab`
**Scope:** the whole repository, plus what the execution environment can and cannot do.
**Rule:** nothing in the application was modified for this audit. Every "current" statement below points to a file in the repo or a command I ran on 2026-10-08.

---

## 1. Executive summary

The repository currently contains a **complete, tested GenAI/RAG application** (layer 2, the "AI Interview Coach"):

- FastAPI backend and web UI.
- PDF/DOCX/TXT extraction.
- Tokenizer-aware chunking.
- MiniLM embeddings with a FAISS index.
- RAG with Gemini through an OpenAI-compatible API.
- Pydantic-validated structured outputs.
- A deterministic match score.
- Interview question generation and answer evaluation.
- 102 passing tests, an evaluation harness and Docker.

**The data-analytics layer (layer 1, "Job Market Intelligence") does not exist yet.** The repository has:

- no pandas;
- no SQL/PostgreSQL;
- no real analytical dataset;
- no statistical tests;
- no scikit-learn model;
- no Tableau/Power BI dashboard;
- no PowerPoint.

The only data in the repository is fictional: 1 sample CV/job pair and 3 CVs × 3 jobs for evaluation. That data is fine for RAG evaluation but **cannot serve as the analytics dataset**.

On the bootcamp checklist, roughly **40 % is satisfied** (GenAI, API/JSON for the LLM, tests, Docker, docs). The remaining mandatory work is concentrated in **data collection → pandas → PostgreSQL → statistics → ML → dashboard → presentation**.

The environment supports all of this, except building the Tableau/Power BI dashboard, which needs a desktop application (see §5).

---

## 2. What exists today (inventory)

| Area | Files | Notes |
|---|---|---|
| App code | `app/` (≈ 3,000 lines of Python) | FastAPI, document processing, embeddings, FAISS, matching, RAG, UI |
| Tests | `tests/` (7 files, 102 tests) | Re-run during this audit: **102 passed** (see §6) |
| Evaluation | `evaluation/run_evaluation.py`, `results_llm.md`, `results_offline.md` | Retrieval, matching, structure, question and answer evaluation. Fictional 3×3 dataset |
| Sample data | `data/examples/` | Fictional CV (TXT/PDF/DOCX) and job description |
| Docs | `README.md`, `docs/demo-script.md`, `docs/presentation-outline.md`, `docs/screenshots/` | RAG-only story. Must be rewritten for the 2-layer product |
| Docker | `Dockerfile`, `docker-compose.yml` | Built and run successfully in the previous session (app only, no DB) |
| Dependencies | `requirements.txt`, `requirements-dev.txt` | No pandas/statsmodels/psycopg/matplotlib/python-pptx |
| Git | 11 commits, PR #1 open | Clean working tree |

**Libraries in the venv (checked):**

| Library | Status |
|---|---|
| numpy 2.5 | installed |
| scipy 1.18 | installed (pulled in by sentence-transformers) |
| scikit-learn 1.9 | installed (same; not used by our code) |
| pandas, statsmodels, psycopg, SQLAlchemy, matplotlib, nbformat/jupyter, python-pptx, requests | **missing** |

**System tools (checked):**

| Tool | Status |
|---|---|
| PostgreSQL 16 server binaries (`initdb`, `pg_ctl`, `postgres`, `psql`) | available |
| LibreOffice | available (can render .pptx to images so slides can be reviewed) |
| Docker | available (daemon must be started) |
| Tableau / Power BI | **not available** (desktop applications) |

---

## 3. Requirement-by-requirement audit

Status legend:
- **MET**: implemented, with evidence.
- **PARTIAL**: exists but does not meet the requirement for the final project.
- **MISSING**: absent.

Priority levels:
- **P0**: mandatory and blocks the story.
- **P1**: mandatory.
- **P2**: quality / optional.

### 3.1 Data handling (Pandas / NumPy)

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **Pandas** | Not used anywhere | MISSING | `grep pandas` returns no code; not in `requirements.txt` | P0 | `src/market/` pipeline built on pandas DataFrames (load → clean → features → export) |
| **NumPy** | Used for embedding matrices, centroids, cosine rescaling | PARTIAL (GenAI side only) | `app/embeddings/service.py`, `app/matching/matcher.py` | P1 | Also use it for analytics: vectorised feature computation, log-salary, percentiles, statistics inputs |
| Data loading | Only text/PDF/DOCX documents | MISSING (tabular) | `app/document_processing/extractors.py` | P0 | Load the real CSV + JSON API snapshots into pandas |
| Data cleaning | Text cleaning only | PARTIAL | `app/document_processing/cleaner.py` | P0 | Tabular cleaning: types, dates, booleans, string normalisation, skill-list parsing |
| Duplicate handling | None for tabular data | MISSING | n/a | P0 | Exact and near-duplicate postings (same title + company + location + date); counts reported before/after |
| Missing values | None for tabular data | MISSING | n/a | P0 | Per-column missing-value report; explicit strategy (keep/flag/drop), e.g. salary is sparse → analysed on its subset only |
| Transformations | n/a | MISSING | n/a | P0 | Parse `job_skills` strings to lists, explode to job×skill, normalise country/remote/schedule, derive seniority |
| Filtering | n/a | MISSING | n/a | P1 | Role/country/date filters in pipeline and SQL |
| Grouping / aggregation | n/a | MISSING | n/a | P1 | Skill demand by role/seniority, remote share by role, salary medians |
| Numerical computations | Cosine rescaling, score weighting | PARTIAL | `app/matching/matcher.py` | P1 | Feature engineering + statistics on the real data |

### 3.2 Database (PostgreSQL / SQL)

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **PostgreSQL** | None (sessions in memory by design) | MISSING | `app/core/sessions.py` | P0 | Postgres 16: local cluster for development + a `postgres` service in `docker-compose.yml` |
| SQL | None | MISSING | n/a | P0 | `sql/schema.sql`, `sql/analysis_queries.sql`, loader using parameterised inserts |
| Tables / schema | None | MISSING | n/a | P0 | Normalised: `companies`, `jobs`, `skills` (with `skill_type`), `job_skills` (M:N), `sources` (+ ingestion metadata) |
| Joins | None | MISSING | n/a | P0 | Skill demand per role (`jobs ⋈ job_skills ⋈ skills`), company/remote analyses |
| Aggregate functions | None | MISSING | n/a | P0 | `COUNT`, `AVG`, `PERCENTILE_CONT` (median salary), `GROUP BY`/`HAVING` |
| Subqueries | None | MISSING | n/a | P1 | E.g. skills whose demand among senior roles exceeds the overall average; jobs above role median salary |
| Ranking / window functions | None | MISSING | n/a | P2 | `RANK() OVER (PARTITION BY role ORDER BY demand)`: top-N skills per role |
| Security / user management | No DB, so none. Secrets handled via `.env` (`.env.example`, `SecretStr`) | PARTIAL | `app/core/config.py`, `.gitignore` | P1 | Separate roles: `coach_owner` (DDL/load) and `coach_reader` (SELECT only, used by the app and the dashboard export); credentials from env; parameterised queries only |
| Views for BI | None | MISSING | n/a | P1 | SQL views feeding the dashboard extracts |

### 3.3 Data collection (API / JSON / scraping)

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **API** | Serves a REST API (FastAPI) and consumes an LLM API (Gemini) | PARTIAL: no data-collection API | `app/api/`, `app/rag/llm.py` | P0 | Ingest a **public job-board JSON API** (see §4) with pagination, polite rate limiting, raw-JSON snapshots |
| **JSON** | Request/response JSON, LLM JSON outputs validated with Pydantic | MET (GenAI side) | `app/models/schemas.py`, `app/rag/llm.py` | P1 | Also raw API JSON → validation (Pydantic) → DataFrame |
| Web scraping and/or external API data collection | None | MISSING | n/a | P0 | **API ingestion** (compliant, documented). Scraping is not needed and is not planned unless the course strictly requires it (open question Q2) |
| **Real analytical dataset** | Only fictional documents | MISSING | `data/examples/`, `evaluation/data/` | **P0** | Main dataset: `lukebarousse/data_jobs` (real 2023 data-job postings, Apache-2.0) + a fresh API snapshot (§4) |
| Raw vs processed separation | n/a | MISSING | n/a | P1 | `data/raw/` (git-ignored except small sample), `data/processed/` |

### 3.4 Statistics

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| Descriptive statistics | Only calibration measurements on 9 fictional pairs | MISSING (on real data) | `app/matching/matcher.py` docstring | P0 | Distributions, central tendency/dispersion of skill count, salary, by role/seniority/remote |
| **SciPy** | Installed, unused | MISSING | n/a | P0 | `scipy.stats`: Mann-Whitney U, chi-square, Spearman, effect sizes |
| **Statsmodels** | Not installed | MISSING | n/a | P1 | OLS on log-salary with categorical controls (role, seniority, remote, skill count) + proportion z-tests; interpretation with CIs |
| Hypothesis testing | None | MISSING | n/a | P0 | Real questions, each with H0/H1, assumptions, statistic, p-value, effect size, limitations (§7) |
| Notebook / reproducible scripts | None | MISSING | n/a | P1 | `notebooks/statistical_analysis.ipynb` **executed** (outputs saved) + scripts it calls |

### 3.5 Machine learning (scikit-learn)

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **Scikit-learn** | Installed, unused | MISSING | n/a | P0 | `src/ml/` pipeline |
| Supervised learning | None (embedding model is pretrained inference, not training) | MISSING | n/a | P0 | Classification problem chosen after EDA (§7) |
| Preprocessing | n/a | MISSING | n/a | P0 | `ColumnTransformer`: multi-hot skills, one-hot categoricals, scaled numerics |
| Train/test split | n/a | MISSING | n/a | P0 | Stratified hold-out split + cross-validation on training data only |
| Baseline | n/a | MISSING | n/a | P0 | `DummyClassifier` (most frequent / stratified) |
| Model training & comparison | n/a | MISSING | n/a | P0 | Logistic Regression vs Random Forest (or Gradient Boosting) |
| Evaluation | n/a | MISSING | n/a | P0 | Accuracy, macro-F1, per-class precision/recall, confusion matrix |
| Hyperparameter tuning | n/a | MISSING | n/a | P1 | `GridSearchCV`/`RandomizedSearchCV` on the training folds |
| Interpretation | n/a | MISSING | n/a | P1 | Coefficients / permutation importance; discuss leakage and limits |
| Saved reproducible results | n/a | MISSING | n/a | P1 | `results/ml/*.json`, plots, fixed random seeds, `joblib` model |

### 3.6 GenAI (existing layer 2)

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **Tokenization** | MiniLM word-piece tokenizer sizes chunks (≤ 200 of 256 tokens) and bounds prompt context | MET | `app/document_processing/tokenizer.py`, `chunker.py` | n/a | Keep |
| **Transformer inference** | `all-MiniLM-L6-v2` (pretrained, inference only) + Gemini LLM | MET | `app/embeddings/service.py`, `app/rag/llm.py` | n/a | Keep. Never describe as "trained" |
| **Vector embeddings** | 384-d L2-normalised embeddings, LRU cache | MET | `app/embeddings/service.py` | n/a | Keep |
| **FAISS** | `IndexFlatIP` + aligned metadata, doc-type filtering | MET | `app/retrieval/faiss_store.py` | n/a | Keep |
| **RAG** | Multi-query / balanced retrieval → numbered sources → grounded prompts → LLM | MET | `app/rag/pipeline.py`, `prompts.py` | n/a | Keep. Add market context (§8) |
| **LLM** | OpenAI-compatible provider; validated with Gemini `gemini-flash-latest` | MET | `app/rag/llm.py`, `evaluation/results_llm.md` | n/a | Keep |
| **Structured outputs** | JSON mode + Pydantic validation + 1 repair + labelled offline fallback | MET | `app/rag/llm.py`, `app/models/schemas.py`; 13/13 valid in evaluation | n/a | Keep |
| Deterministic scoring (40/35/15/10) | Implemented and configurable; weights verified in code and tests | MET | `app/matching/matcher.py` (`DEFAULT_WEIGHTS`), `app/core/config.py`, `tests/test_matching.py::test_combine_renormalises_missing_signals` | n/a | Keep. Explain in deck why the LLM does not set the score |
| GenAI evaluation | Recall@k/MRR, matching consistency, JSON validity, question relevance, answer consistency | MET (small fictional set) | `evaluation/results_llm.md` | P2 | Keep; label clearly as a small evaluation |

### 3.7 Dashboard

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **Interactive dashboard** | None (the web UI is the coach, not an analytics dashboard) | MISSING | n/a | **P0** | Tableau Public (recommended) or Power BI: "AI & Tech Job Market Insights" |
| Tableau **or** Power BI | Not available in the container; cannot be built or verified here | MISSING · **manual step** | `which` finds neither | P0 | I prepare clean extracts (from SQL views), a precise dashboard spec and click-by-click steps; **you build and publish it**; screenshots only after it exists |
| Title + filters + dynamic graphs | n/a | MISSING | n/a | P0 | Filters: role, seniority, country, remote, schedule, month, skill. 6–8 linked views (spec in Phase 7) |

### 3.8 Product, presentation, portfolio

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| Coherent product story (2 layers) | RAG-only story | PARTIAL | `README.md` | P0 | Market context inside the coach (§8) + rewritten README/deck |
| **PowerPoint** | None (only a Markdown outline for the RAG-only talk) | MISSING | `docs/presentation-outline.md` | **P0** | `demo_day/presentation/SLIDE_CONTENT.md` first, then a 13–15 slide .pptx generated with python-pptx from real charts/screenshots, rendered to PNG via LibreOffice for review; speaker notes for 3-min and 15–20-min modes |
| Demo Day script / checklist | 2–3 min RAG-only script (timings estimated, not measured) | PARTIAL | `docs/demo-script.md` | P0 | `demo_day/demo_script.md` + `demo_checklist.md`, timed by actually running the flow |
| Portfolio entry | None | MISSING | n/a | P1 | `demo_day/portfolio/portfolio_entry.md` |
| Screenshots | 2 real UI screenshots (RAG side) | PARTIAL | `docs/screenshots/` | P1 | Re-capture after UI changes; dashboard screenshots from your published dashboard |

### 3.9 Engineering quality

| Official requirement | Current implementation | Missing? | Evidence | Priority | Planned solution |
|---|---|---|---|---|---|
| **Automated tests** | 102 tests, deterministic, offline | MET (GenAI); MISSING (analytics) | `tests/`; `pytest` → 102 passed | P1 | Add tests for cleaning, features, skill parsing, SQL load (against a temporary Postgres DB), ML pipeline, API ingestion (mocked HTTP), dashboard-extract shape |
| Documentation | Complete for the RAG layer | PARTIAL | `README.md` | P1 | `docs/ARCHITECTURE.md`, `DATA_PIPELINE.md`, `DATABASE.md`, `STATISTICAL_ANALYSIS.md`, `MACHINE_LEARNING.md`, `RAG.md`, `EVALUATION.md`; README rewrite at the end |
| **Docker** | App image built and run (previous session) | PARTIAL (no DB) | `Dockerfile`, `docker-compose.yml` | P1 | Add `postgres` service + init scripts; verify `docker compose up` end-to-end |
| Reproducibility | Pinned-range deps, seeds N/A, model baked in Docker | PARTIAL | `requirements*.txt` | P1 | `make`-style scripts: download → clean → load → analyse → train → export, with checksums and fixed seeds |
| Secrets | `.env` git-ignored, `SecretStr`, no keys in repo (scan done last session) | MET | `.gitignore`, `.env.example` | P1 | Repeat the scan at the end; add `DATABASE_URL` to `.env.example` without real values |
| Logging / error handling | Present, no personal data logged | MET | `app/core/logging.py`, `app/main.py` | n/a | Same discipline for the pipeline |

---

## 4. Data source assessment (checked 2026-10-08)

All checks were read-only requests for metadata or the first page of results.

| Source | Type | Reachable | License / terms | Fields useful here | Verdict |
|---|---|---|---|---|---|
| **`lukebarousse/data_jobs`** (Hugging Face) · https://huggingface.co/datasets/lukebarousse/data_jobs | Real job postings (2023, data roles) collected by Luke Barousse from Google Jobs via SerpApi; CSV 231,152,089 bytes | ✅ 200 | **Apache-2.0** (dataset card) | `job_title_short` (10 classes incl. *Senior* Data Analyst/Engineer/Scientist), `job_title`, `job_location`, `job_country`, `job_via`, `job_schedule_type`, `job_work_from_home`, `job_posted_date`, `job_no_degree_mention`, `job_health_insurance`, `salary_year_avg` (sparse), `company_name`, `job_skills` (list), `job_type_skills` (skill → category) | **Primary analytics dataset.** Row count, missing values and duplicates will be **measured** in Phase 2–3 (not assumed) |
| **Arbeitnow Job Board API** · https://www.arbeitnow.com/api/job-board-api | Live public JSON API, 325 jobs/page, paginated, updated hourly | ✅ 200 | Free public API: "please do not abuse… linking back appreciated… agree to the ToS"; `robots.txt` allows all | `title`, `company_name`, `description` (HTML), `remote`, `tags`, `job_types`, `location`, `created_at`, `url` | **Live API + JSON ingestion** (small, rate-limited snapshot) and a source of **real job descriptions** for the coach demo (with link-back attribution) |
| Remotive API · https://remotive.com/api/remote-jobs | Live public JSON API (remote jobs only, 24 h delay) | ✅ 200 | Must link back and credit Remotive; **max ~4 requests/day**; no redistribution to job boards | Similar to Arbeitnow + `category`, `salary` | Optional second API; strict terms, so only if needed |
| The Muse API, RemoteOK API, HN Algolia | Public JSON | ✅ 200 | Terms not yet reviewed | n/a | Not needed |
| USAJOBS API | Public with key | 401 (needs a key) | Gov terms | n/a | Not needed |
| Kaggle datasets | Download needs Kaggle credentials | listing ✅ | Varies | n/a | Not needed (HF dataset is openly downloadable) |

**Known limitations of the primary dataset (to be documented and quantified, not hidden):**

1. Data/analytics roles only, not the whole tech market.
2. Collected in 2023.
3. Collected from Google Jobs search results, so the country mix reflects the collector's search locations.
4. Skills are keyword-extracted by the author, not from full descriptions; the dataset has no description text.
5. `job_title_short` was produced by the author's BERT classifier, so it is a derived label.
6. Salary is available for a minority of rows only.
7. "Seniority" is only observable as *Senior …* vs the rest; there is no junior label. Deriving junior/mid from raw titles (`junior`, `jr`, `lead`, `principal`) is possible and will be measured before relying on it.

**Scraping:** not required, because the requirement is "API and/or scraping". I recommend **no scraping**. The API route is cleaner legally, and Remotive's `robots.txt` explicitly disallows `/jobs/*` pages anyway. If your course demands a scraping component specifically, see open question Q2.

---

## 5. What cannot be done from this environment

| Item | Why | What I will do instead |
|---|---|---|
| Build / publish the Tableau or Power BI dashboard | Desktop applications are not available in the Linux container, and publishing needs your account | Clean extracts (`demo_day/assets/dashboard_data/*.csv`) produced from SQL views, an exact dashboard spec, and step-by-step build instructions. Marked **MANUAL STEP REQUIRED** until you send me the link/screenshots |
| Dashboard screenshots in the deck | They must come from the real dashboard | Placeholder slide clearly labelled "insert screenshot", **not** a mock-up |
| Rehearse the talk | Needs you | Timed demo run of the software parts by me; spoken timings estimated by word count and labelled as such |

---

## 6. Verification done during this audit

| Check | Result |
|---|---|
| `pytest` | 102 passed (re-run on commit `cd4eaab` before the audit; no code changed since) |
| Weights 40/35/15/10 | Present in `DEFAULT_WEIGHTS` and settings defaults; re-normalisation tested |
| Data sources | See §4 (HTTP status and headers checked; terms read from source) |
| PostgreSQL | Server binaries v16 present at `/usr/lib/postgresql/16/bin`; no cluster running yet |
| Secrets | Previous full scan clean; no code changes since |

---

## 7. Proposed analyses and ML problem (to be confirmed on the data, Phase 5–6)

Candidate statistical questions. Each will only be kept if the data supports it, with the test chosen after checking the distributions.

| # | Question | Likely method |
|---|---|---|
| A | Do senior postings list more skills than non-senior postings of the same role family? | Descriptives; Mann-Whitney U (skill counts are discrete and skewed); effect size (rank-biserial) |
| B | Is remote work associated with role family? | Contingency table + chi-square test of independence; Cramér's V |
| C | Which skills are over-represented in senior roles? | Per-skill 2×2 chi-square / two-proportion z-test with multiple-testing correction (Benjamini-Hochberg) |
| D | Which factors are associated with advertised salary (subset with salary)? | Statsmodels OLS on log-salary with role, seniority, remote, skill count; robust SE; association, not causation |

ML candidates. The final choice will be made after EDA, and in particular after checking class balance and leakage.

| Option | Target | Features | Pros / cons |
|---|---|---|---|
| **1. Role family from skill profile** (recommended) | Data Analyst / Data Engineer / Data Scientist / ML Engineer / … (merged to ~4–6 classes) | Multi-hot skills, skill-type counts, remote, schedule, degree flag | Strong signal. **Directly reusable in the coach**: "your CV's skill profile looks like a *Data Engineer* posting". Must exclude title text (the label was derived from the title) |
| 2. Senior vs non-senior | Binary from `job_title_short` | Same, excluding title | Matches the brief, but the signal from skills alone may be weak and the classes imbalanced; still a legitimate, honestly-reported experiment |
| 3. Salary band | Tertiles of `salary_year_avg` | Same | Only on the salary subset; country confounding |

Recommendation: **Option 1 as the main model, Option 2 as a secondary experiment** if time allows, reported honestly even if the performance is modest.

---

## 8. How the two layers will connect (planned)

The connection is through the data itself, not just the story.

1. **Market context in the coach.** After analysing a CV/job pair, the coach queries PostgreSQL (read-only role) for each matched or missing skill: "AWS appears in X % of *Machine Learning Engineer* postings (n = …) in the 2023 dataset". This turns a gap into a prioritised gap, and the LLM receives these numbers as computed facts (it is told not to change them).
2. **Role-profile prediction.** The trained scikit-learn model (Option 1) is applied to the skills extracted from the CV, giving the predicted role family with its probability. This is shown as a market-positioning signal, not as a verdict.
3. **Real job descriptions.** The demo can load a real posting from the API snapshot (with attribution) instead of only the fictional job.

Skill vocabularies differ: the dataset uses lowercase names such as `aws` and `power bi`, while the coach uses canonical names. A tested mapping table will reconcile them, and unmatched skills will be reported.

---

## 9. COURSE COMPLIANCE SCORECARD

The 62 rows of §3 grouped into 47 requirements. Related rows are merged: for example, the whole scikit-learn pipeline counts once. A requirement that is met on the GenAI side but missing on the analytics side counts once, as PARTIAL.

| Status | Count | Requirements |
|---|---|---|
| **Already satisfied** | 14 | JSON (GenAI side), tokenization, transformer inference, vector embeddings, FAISS, RAG, LLM, structured outputs, deterministic scoring, GenAI evaluation, secrets handling, logging/error handling, FastAPI REST API, web UI for the coach |
| **Partially satisfied** | 10 | NumPy (GenAI only), text cleaning (not tabular), numerical computations, API (no data-collection API), DB security (no DB yet), tests (no analytics tests), docs (RAG only), Docker (no DB), reproducibility (no data pipeline), demo script / screenshots (RAG only, timings not measured) |
| **Missing (mandatory)** | 23 | Pandas, tabular loading/cleaning, duplicates, missing values, transformations, filtering, grouping, PostgreSQL, SQL schema, joins, aggregates, subqueries, external data collection, real dataset, descriptive statistics, SciPy tests, Statsmodels, hypothesis testing, scikit-learn pipeline (split/baseline/models/evaluation/tuning/interpretation), interactive dashboard (Tableau/Power BI), PowerPoint, portfolio, two-layer product story |

### Optional improvements
- Window functions (`RANK() OVER`) for top-N skills per role.
- A second live API (Remotive) for remote-only comparison.
- Seniority experiment (ML Option 2).
- A GitHub Actions CI workflow running `pytest`.
- Executed notebooks rendered to HTML for the portfolio.

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Dashboard is a manual step outside my control | P0 requirement could remain incomplete | Prepare everything so the build takes about 1–2 h. Start it early (Phase 7) and don't leave it to the end |
| Dataset size (231 MB, row count to be measured; likely hundreds of thousands of rows) | Slow downloads in Docker/CI; repository bloat | Never commit raw data; download script with size/checksum check; commit a small reproducible sample + aggregates; optional row sampling flag |
| Weak ML signal for seniority | "Bad" metrics | Choose the role-family problem as the main model; report seniority honestly as an experiment |
| Label leakage (`job_title_short` derived from `job_title`) | Inflated metrics | Exclude title-derived features; document it |
| Source bias (2023, data roles, Google-Jobs-based, country mix) | Over-general claims | State it on the dataset slide and in the README; all claims phrased as "in this dataset" |
| Live dependencies on Demo Day (Gemini API, Tableau Public online) | Demo failure | Labelled offline fallback (already exists); dashboard screenshots as backup slide; local Postgres in Docker |
| Scope creep / time | Unfinished project | Phases in order, each tested and committed; the GenAI layer is already done and must not regress (tests stay green) |
| Two skill vocabularies | Wrong market numbers in the coach | Explicit mapping table + test + "unmatched" report |

### Recommended implementation order
1. **Phase 2: data source + ingestion.** Download the HF dataset (checksum, metadata) and build the Arbeitnow API ingester (pagination, ≤ 1 request/s, raw JSON snapshots, Pydantic validation).
2. **Phase 3: pandas/NumPy cleaning + features**, with a before/after report generated by code.
3. **Phase 4: PostgreSQL schema, load, roles, SQL analysis queries, views**, plus Docker Compose with Postgres.
4. **Phase 5: statistics.** Executed notebook + `docs/STATISTICAL_ANALYSIS.md`.
5. **Phase 6: ML.** Baseline → 2 models → CV tuning → test evaluation → saved results.
6. **Phase 7: dashboard extracts + spec + build instructions.** **You build it in Tableau Public / Power BI** (start in parallel with Phase 8).
7. **Phase 8: integration in the coach.** Market context + role profile + real job descriptions.
8. **Phase 9: tests + evaluation** (analytics and GenAI).
9. **Phase 10: demo preparation.** Timed run.
10. **Phase 11: PowerPoint** (SLIDE_CONTENT.md → .pptx → rendered review).
11. **Phase 12: final compliance matrix**, README rewrite, secrets scan, full QA.

---

## 10. Open questions (decisions that are yours)

| # | Question | Default if no answer |
|---|---|---|
| Q1 | **Tableau or Power BI?** Which can you install? (Power BI Desktop is Windows-only, and "Publish to web" needs a work/school account; Tableau Public is free on Mac and Windows and gives a public link) | Tableau Public |
| Q2 | Does your course require **web scraping specifically**, or is "API and/or scraping" satisfied by a public JSON API? | Public API only, no scraping |
| Q3 | Is the **primary dataset** acceptable: 2023 data-job postings (`lukebarousse/data_jobs`, Apache-2.0) + a fresh Arbeitnow API snapshot? | Yes |
| Q4 | **Product name**: "AI Job Market & Interview Coach". Rename the GitHub repo, or keep `ai-job-interview-coach`? | Keep repo name, change product title |
