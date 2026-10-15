# Scope application vs delivered project

This page checks the project against the **Final Project Scope Application** submitted at the start ("AI Job Interview & Application Coach"). Every "done" line points to code or results in this repository.

**Name:** the scope used the working title *AI Job Interview & Application Coach*. The delivered product is called *AI Job Market & Interview Coach* because it adds a job-market analytics layer (Layer 1: 787,923 postings, PostgreSQL, statistics, ML, Tableau) on top of the scoped coach (Layer 2). The coach itself is the scoped MVP.

## Planning (10 tasks)

| # | Task | Status | Evidence |
|---|---|---|---|
| 1 | Architecture, example CVs and job descriptions | Done | `README.md` (Architecture), `data/examples/`, `evaluation/data/` (3 CVs × 3 jobs) |
| 2 | Text extraction and preprocessing | Done | `app/document_processing/extractors.py` (PDF, DOCX, TXT, MD) |
| 3 | Cleaning, chunking, tokenization | Done | `cleaner.py`, `chunker.py` (≤ 200 tokens, 30-token overlap), `tokenizer.py` (Hugging Face tokenizer of the embedding model) |
| 4 | Vector embeddings | Done | `app/embeddings/service.py` (`all-MiniLM-L6-v2`, pretrained, inference only) |
| 5 | FAISS index and semantic retrieval | Done | `app/retrieval/faiss_store.py` (`IndexFlatIP`), `retriever.py` |
| 6 | RAG pipeline | Done | `app/rag/pipeline.py`, `prompts.py` (numbered sources `[S#]`), `llm.py` (Gemini via an OpenAI-compatible API) |
| 7 | Matching and skill-gap analysis | Done | `app/matching/` (skills 40 %, requirements 35 %, semantic similarity 15 %, experience 10 %) |
| 8 | Interview questions and answer evaluation | Done | `app/rag/interview_planner.py`, `pipeline.py`; rubric with 4 criteria |
| 9 | Web interface and API | Done | `app/ui/static/`, `app/api/routes/`; live at <https://ai-job-interview-coach-291756431151.europe-west1.run.app/> |
| 10 | Testing, evaluation, documentation | Done | 195 tests (`tests/`), `evaluation/results_llm_2026-10-12.md`, `README.md`, `docs/` |

## Features

### Minimum viable product (all done)

| # | Feature | Where to see it |
|---|---|---|
| 1 | Upload or paste a CV | Step 1 of the UI: file button or text area |
| 2 | Upload or paste a job description | Same, right column |
| 3 | Extract skills, experience and job requirements | `app/matching/skills.py`, `requirements.py`; "Requirement coverage" panel |
| 4 | Compare the CV with the job offer | Match score and breakdown |
| 5 | Identify missing skills and experience gaps | "Missing skills" (required / nice to have) and "Gaps" |
| 6 | RAG-based interview assistant | Every question and evaluation is generated from retrieved passages, shown under "Sources" |
| 7 | Personalised interview questions | Step 3, five question types (auto, technical, experience, skill gap, behavioral) |
| 8 | AI feedback on answers | Score /10, 4 rubric criteria, strengths, weaknesses, missing points, stronger answer |
| 9 | Personalised preparation recommendations | "Recommendations" in the AI insights, plus market demand for each missing skill |
| 10 | Simple web interface | FastAPI + HTML/CSS/JS, no build step |

### Additional features (optional in the scope)

| # | Feature | Status | Notes |
|---|---|---|---|
| 1 | Multiple CV formats | Done | PDF, DOCX, TXT, Markdown |
| 2 | Automatic document summarization | Partial | The AI insights summarise the CV/job fit in 2–4 sentences; there is no separate summary of each document |
| 3 | Automatic skill categorization | Done | 99-skill taxonomy with categories (Cloud, DevOps, AI/ML, Soft skills…) |
| 4 | Match score visualization | Done | Score ring and weighted bars with hover explanations |
| 5 | Personalised learning recommendations | Done | Recommendations + how often the market asks for each missing skill |
| 6 | Multi-job comparison | Not done | Only offline, in the evaluation (3 CVs × 3 jobs matrix) |
| 7 | Adaptive interview difficulty | Not done | Each question has a difficulty label; it does not adapt to previous answers |
| 8 | Interview performance dashboard | Partial | Session history lists every answer with its score; no aggregated view |
| 9 | Interview history | Done | "Session history" in step 3 (kept for the session, not stored) |
| 10 | Voice-based interview simulation | Not done | |

**Beyond the scope:** job-market analytics (Layer 1), market demand inside the coach, the Tableau Public dashboard, Docker and the Cloud Run deployment.

## Tools and frameworks

| Tool | Scope | Used | Evidence |
|---|---|---|---|
| JSON | Yes | Yes | Structured LLM outputs validated with Pydantic (`app/models/schemas.py`); API payloads; Arbeitnow API ingestion |
| API | Yes | Yes | REST API (FastAPI, `/docs`), LLM API, Arbeitnow public API |
| Python | Yes | Yes | Whole project |
| Vector embeddings | Yes | Yes | MiniLM, 384 dimensions |
| Transformer inference | Yes | Yes | Sentence-transformer encoder (inference only) + LLM |
| LoRA adapters | No | No | |
| FAISS | Yes | Yes | `IndexFlatIP` with normalised vectors (cosine similarity) |
| Tokenization | Yes | Yes | Token-aware chunking with the embedding model's tokenizer |
| Retrieval-Augmented Generation | Yes | Yes | Retrieval before every generation, sources cited |
| Feature engineering | Yes | Yes | 59 features for the role classifier (`market/ml/`), match-score components |
| Supervised learning | Maybe | Yes | Role-family classifier (`docs/MACHINE_LEARNING.md`) |
| Unsupervised learning | Maybe | No | |
| Overfitting | Maybe | Yes | Company-grouped split, model selection on cross-validation only (`docs/MACHINE_LEARNING.md` §3) |
| Loss function | Maybe | Yes | Cross-entropy (log loss) for logistic regression and gradient boosting |
| Regularization | Maybe | Yes | L2 penalty tuned by cross-validation; depth, leaf and learning-rate limits for the trees |

## Evaluation focus

The scope named three evaluation targets. Results from `evaluation/results_llm_2026-10-12.md` (Gemini):

| Target | Result |
|---|---|
| Retrieval relevance | 12 labelled queries: hit@1 67 %, hit@3 92 %, MRR 0.81 |
| CV/job matching quality | 3 CVs × 3 jobs: each CV scores highest on its own job (mean 94.3 vs 31.8); identical score on a repeated run |
| Usefulness and relevance of questions and feedback | Requested category respected 100 %; questions mention a job skill 83 %; answer scores ordered strong 8.0 > average 2.6 > off-topic 0.1, spread ≤ 0.4 between repeats; 13/13 LLM outputs valid JSON on the first try |
