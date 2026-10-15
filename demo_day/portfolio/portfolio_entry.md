# Portfolio entry: AI Job Market & Interview Coach

**One-liner:** From job-market data to personalised interview preparation. An analytics pipeline over about 788,000 job postings, combined with a RAG-based AI coach that compares a CV with a job and runs a mock interview.

**Role:** sole developer (data engineering, analysis, ML, GenAI, web app) · Data Science & GenAI Bootcamp final project

## Problem

Candidates prepare blindly. They don't know which skills the market asks for, how well their CV fits a specific job, or how to answer the questions an interviewer will ask about their gaps. Generic AI chats invent experience and give unexplained scores.

## Solution

1. **Job-market analytics:**
   - 3,026 live postings (Arbeitnow public API, Oct 2026) and 784,897 reference postings (Hugging Face `data_jobs`, 2023), cleaned with pandas;
   - loaded into PostgreSQL (4.5 M rows, read-only analysis role) and analysed with 15 SQL queries;
   - statistical tests with effect sizes (SciPy, statsmodels);
   - a scikit-learn classifier;
   - a Tableau Public dashboard.
2. **AI Interview Coach:**
   - a FastAPI web app: CV and job description → chunking → MiniLM embeddings → FAISS → explained match score;
   - market demand for the missing skills;
   - LLM-generated interview questions and rubric-based feedback, grounded in retrieved passages, with validated JSON outputs and an offline fallback.

## Results

- Role classifier: macro-F1 **0.393** vs **0.142** for a stratified baseline (accuracy 0.639, top-3 accuracy 0.929), with a company-grouped split.
- Statistics: senior status associated with **+17.2 %** advertised salary (OLS, R² 0.26). Effect sizes are reported for every test.
- Coach: retrieval hit@3 **92 %**; matching CV/job pairs score **94.3** vs **31.8** for mismatched pairs; **13/13** LLM outputs valid on first try.
- **195** automated tests, including a real temporary PostgreSQL server.

## Technologies

Python · pandas · NumPy · PostgreSQL · SQL · SciPy · statsmodels · scikit-learn · matplotlib · Tableau Public · sentence-transformers · FAISS · RAG · LLM (Gemini via OpenAI-compatible API) · FastAPI · Pydantic · Docker · pytest

## Links

- GitHub: https://github.com/Raphzaf/ai-job-interview-coach
- Live demo: https://ai-job-interview-coach-291756431151.europe-west1.run.app/
- [ ] 2-minute video
- Tableau Public dashboard: https://public.tableau.com/app/profile/raphael.zafran/viz/AIJobMarketInterviewCoachMarketDashboards/D1-Overview
- [ ] Technical article

## Screenshots

- `docs/screenshots/analysis-with-market.png`: match analysis with market context
- `docs/screenshots/interview-feedback.png`: interview feedback
- [ ] Tableau dashboard screenshot
