# Trello board (for slide 4 of the template)

The template asks for a screenshot of a Trello board showing the feature list. Trello's free plan has no import, so here is the content to create by hand. It takes about 10 minutes.

**Board name:** AI Job Market & Interview Coach

**Lists:** `Backlog` · `In progress` · `Done`

**Labels:**
- `Data` (blue)
- `SQL` (purple)
- `Stats/ML` (orange)
- `GenAI` (green)
- `App` (yellow)
- `Delivery` (red)

## Done

| Card | Label |
|---|---|
| Collect job postings from the Arbeitnow public API (3,026 postings) | Data |
| Download and verify the data_jobs reference dataset (784,897 postings) | Data |
| Clean data, extract skills, build features (pandas, NumPy) | Data |
| PostgreSQL schema, read-only role, loader (4.5 M rows) | SQL |
| 15 analytical SQL queries | SQL |
| Statistical tests with effect sizes (SciPy, statsmodels) | Stats/ML |
| Role-family classifier (scikit-learn, macro-F1 0.393) | Stats/ML |
| Tableau data extracts + 16 validation checks | Data |
| CV/job extraction, cleaning, token-aware chunking | GenAI |
| Embeddings (MiniLM) + FAISS semantic search | GenAI |
| RAG pipeline with sources + validated JSON outputs | GenAI |
| Explained match score | App |
| Market demand for missing skills in the coach | App |
| Interview questions + answer feedback | GenAI |
| Web UI + REST API | App |
| 191 automated tests + GenAI evaluation | Delivery |
| Docker image | Delivery |
| README + documentation | Delivery |

## In progress

Move each card to *Done* once it is finished:

| Card | Label |
|---|---|
| Build and publish the Tableau Public dashboard | Data |
| Deploy the coach (Hugging Face Space) | Delivery |
| Record the 2-minute demo video | Delivery |
| Slides from the official template | Delivery |
| Technical article + portfolio entry | Delivery |

## Backlog

| Card | Label |
|---|---|
| Scheduled refresh of the live job data | Data |
| Multilingual CVs and job ads | GenAI |
| Adaptive interview difficulty | GenAI |
| Persistent progress tracking | App |

**Tip for the screenshot:** collapse the card descriptions, zoom out to about 80 % so the three lists fit, and take the capture after moving the finished cards to *Done*.
