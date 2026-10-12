# Final Project: Compliance Matrix

**Updated:** 2026-10-12 (the Phase 1 audit of 2026-10-08 is in the Git history of this file).

**Status labels:**
- **DONE:** implemented and verified in this repository.
- **MANUAL:** requires your accounts or desktop tools; everything that can be prepared is ready.
- **TO CONFIRM:** depends on the official instructions, which are not in the repository.

**Requirement sources:**
1. The official Google Slides template "New_Template_Final project" (inspected 2026-10-12).
2. The project brief's list of required technologies.

## Required technologies

| Requirement | Status | Evidence |
|---|---|---|
| Python, JSON | DONE | `market/`, `app/`; API JSON ingestion with Pydantic validation |
| Pandas, NumPy | DONE | `market/cleaning_*.py`, `market/text.py`; reports in `data/processed/reports/*.json` |
| PostgreSQL + SQL | DONE | `sql/`, `market/db/`; 4,478,391 rows; 15 queries with results in `data/processed/sql_results/`; tests on a real temporary server |
| Statistical analysis | DONE | `market/stats/`, `notebooks/statistical_analysis.ipynb`, `docs/STATISTICAL_ANALYSIS.md` |
| scikit-learn ML | DONE | `market/ml/`, `models/role_classifier.joblib`, `notebooks/ml_analysis.ipynb`, `docs/MACHINE_LEARNING.md` |
| Interactive dashboard (Tableau / Power BI) | **MANUAL** | Data, validation, spec and build guide are ready in `dashboard/`. The workbook must be built and published in Tableau Public. |
| Pretrained embeddings, transformer inference, tokenization | DONE | `app/embeddings/`, `app/document_processing/tokenizer.py` |
| Vector search (FAISS) + RAG + LLM + structured outputs | DONE | `app/retrieval/`, `app/rag/`; evaluation in `evaluation/` |
| Integration of the data layer into the application | DONE | `app/market_context/` (Phase 8), `tests/test_market_context.py` |
| Automated tests | DONE | 159 tests passing (`pytest`) |
| Documentation | DONE | `README.md`, `docs/*.md` |
| Docker / reproducibility | DONE | `Dockerfile`, `docker-compose.yml` (coach + optional `db` profile); reproduction commands in the README |

## Template deliverables (slides 4–6)

| Deliverable | Status | Where / what is left |
|---|---|---|
| Slides following the template | **MANUAL** | Content mapped slide by slide: `demo_day/SLIDES_CONTENT.md` |
| Trello screenshot (feature list) | **MANUAL** | Board content: `demo_day/TRELLO_BOARD.md` |
| GitHub link | DONE | https://github.com/Raphzaf/ai-job-interview-coach |
| 2-minute video | **MANUAL** | Script and checklist: `demo_day/DEMO_SCRIPT.md` |
| Deployed link | **MANUAL** | Hugging Face Space ready to push: `deploy/huggingface/` (app verified in a container on 2026-10-12) |
| Portfolio link | **MANUAL** | Content: `demo_day/portfolio/portfolio_entry.md` |
| Technical article link | **MANUAL** | Draft: `docs/TECHNICAL_ARTICLE.md` |
| CV, LinkedIn, job tracker links | **MANUAL** | Personal |
| Roadmap, next step | DONE (content) | `demo_day/SLIDES_CONTENT.md`, slides 7–8 |

## Open questions (TO CONFIRM with the official instructions)

1. **Video length:** the template says a 2-minute video; another brief says 3–4 minutes. `demo_day/DEMO_SCRIPT.md` has a 2-minute core plus optional extensions.
2. **Slides for data, statistics, ML and dashboard:** the 8-slide template has none. Backup slides B1–B4 are prepared in case they are expected.
3. **Is the dashboard mandatory?** The project brief says the official instructions require it; the template does not mention it. It is prepared either way.
