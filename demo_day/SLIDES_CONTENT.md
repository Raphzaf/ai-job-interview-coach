# Slide content, mapped to the official bootcamp template

**Template:** "New_Template_Final project" (Google Slides, 8 slides), inspected on 2026-10-12. Its structure is followed exactly below. The template has no slide for data, statistics, ML or the dashboard, although the project brief asks for them. They are therefore proposed as **optional backup slides (B1–B4)** after slide 8. Keep or drop them according to the official instructions.

**Rules followed:**
- no code on the slides;
- real screenshots and figures from the project only;
- every number taken from a saved result file.

The `[ ]` items are things only you can provide.

---

## Slide 1: `<MY PROJECT NAME>`

**AI Job Market & Interview Coach**
*From job-market data to personalised interview preparation*

[ ] Your name · Data Science & GenAI Bootcamp · date

> **Notes:** "My project uses job-market data to understand what employers want, then an AI coach helps a candidate prepare for one specific job."

---

## Slide 2: Project name, description, problem

**Problem:**
- Job seekers prepare blindly: they don't know what the market asks for, how their CV matches a given job, or how to answer the questions that will come.
- Generic AI chats invent experience and give unexplained "match percentages".

**Solution, in two layers:**
1. **Job-market analytics:** about 788,000 postings → PostgreSQL → statistics, ML and a Tableau dashboard. *What do employers want?*
2. **AI Interview Coach:** CV + job → semantic search (RAG) → explained match score, market demand for the missing skills, personalised interview questions and grounded feedback. *How do I prepare?*

**Visual:** `docs/screenshots/analysis-with-market.png` (crop the score + market panel).

> **Notes:** "The key idea: data tells you what the market wants; the AI tells you what that means for *your* CV and *this* job."

---

## Slide 3: Stack

Group the logos/labels by role, not as a flat list:

| Data & analytics | Database | Statistics & ML | GenAI | App & delivery |
|---|---|---|---|---|
| Python, pandas, NumPy, Jupyter | PostgreSQL 16, SQL | SciPy, statsmodels, scikit-learn | sentence-transformers (MiniLM), FAISS, LLM via OpenAI-compatible API (Gemini), RAG | FastAPI, HTML/CSS/JS, Docker, pytest, Tableau Public, Git/GitHub |

> **Notes:** "Every tool has a job. PostgreSQL stores 4.5 million rows with a read-only role. Statistics test hypotheses with effect sizes. scikit-learn measures how much skills say about a role. FAISS and the LLM power the coach."

---

## Slide 4: Feature list

**Template instruction:** "Make a screenshot of your trello". [ ] Create the board from `demo_day/TRELLO_BOARD.md`, then paste a screenshot here.

If the screenshot is too dense, add 5 short bullets next to it:
- Market dashboard: skills by role, seniority, country, remote (Tableau Public)
- Statistical analysis + role classifier (macro-F1 0.393 vs 0.142 baseline)
- Explained CV/job match score with CV evidence per requirement
- Market demand for the missing skills (e.g. AWS: 31.1 % of ML Engineer postings)
- Personalised interview questions + rubric feedback with sources

---

## Slide 5: Links

| Link | Value |
|---|---|
| GitHub | https://github.com/Raphzaf/ai-job-interview-coach |
| 2-min video | [ ] unlisted YouTube/Loom link (script: `demo_day/DEMO_SCRIPT.md`) |
| Deployed link | https://ai-job-interview-coach-291756431151.europe-west1.run.app/ |
| Portfolio link | [ ] your portfolio page (content: `demo_day/portfolio/portfolio_entry.md`) |
| Technical article link | [ ] Medium/LinkedIn/dev.to article (draft: `docs/TECHNICAL_ARTICLE.md`) |
| Dashboard (extra) | https://public.tableau.com/app/profile/raphael.zafran/viz/AIJobMarketInterviewCoachMarketDashboards/D1-Overview |

---

## Slide 6: Career Prep

[ ] CV link · [ ] LinkedIn link · [ ] Job tracker link (personal; not part of the repository)

> **Tip:** the coach itself is a nice story here. "I used my own tool on my CV against the jobs I'm applying for."

---

## Slide 7: Roadmap

The template shows a timeline grid with "Feature X / Y / Z". Suggested rows, past and next:

| Feature | Status |
|---|---|
| GenAI coach: RAG, match score, interview practice | ✅ Done (week 1) |
| Job-market data pipeline + PostgreSQL + SQL | ✅ Done (week 1–2) |
| Statistics + ML classifier | ✅ Done (week 2) |
| Market context inside the coach | ✅ Done (week 2) |
| Tableau Public dashboard | ✅ Done (week 3) |
| Deployment (Google Cloud Run) | ✅ Done (week 3) |
| **Next:** scheduled data refresh, multilingual support, adaptive interview difficulty | Planned |

[ ] Adjust the week labels to your real calendar. The Git history shows the first commit on 2026-10-08.

---

## Slide 8: My next step

Suggested:
- Refresh the live job data on a schedule, to measure real trends over time (today: one snapshot only).
- Use the classifier to suggest the role when a job title is ambiguous.
- Multilingual CVs and job ads (French, German, Hebrew).
- [ ] Personal next step: the role you are targeting, and how this project supports it.

---

## Optional backup slides (use if the instructions ask for data/ML/dashboard, or for Q&A)

### B1: Data

| | Arbeitnow API | lukebarousse/data_jobs |
|---|---|---|
| Period | Snapshot of 8 Oct 2026 | 2023 |
| Postings | 3,026 | 784,897 |
| Scope | All jobs, mostly Germany | Data/tech roles, worldwide |

**Pipeline:** cleaning → skills extracted with one shared 99-skill taxonomy → PostgreSQL, 4,478,391 rows, read-only analysis role, 15 SQL analyses. The two sources are never compared over time.

### B2: Statistics

**Visual:** `reports/figures/stats/C_senior_skill_odds_ratios.png`.

**Message:** "With 785k rows everything is significant, so I report effect sizes."
- Senior postings list slightly more skills (small effect).
- Senior status is associated with +17.2 % advertised salary (OLS, R² 0.26).
- 64 of 71 skills are associated with seniority within the same role.

### B3: Machine learning

**Visual:** `reports/figures/ml/ML_model_comparison.png` or `ML_confusion_matrix.png`.

**Role classifier from skills:**
- macro-F1 **0.393** vs **0.142** for a stratified baseline;
- accuracy 0.639; top-3 accuracy 0.929;
- company-grouped split, so the model cannot memorise companies.

**Honest negative result:** seniority from skills is weak, with AUC 0.625.

### B4: Dashboard

Real screenshots of the published dashboard, numbers checked against `dashboard/tableau/EXPECTED_VALUES.md`: `demo_day/screenshots/dashboard_overview.png`, `dashboard_filtered_de_germany.png` (Data Engineer + Germany) and `dashboard_live.png`.

---

## Spoken pitch for a 2–3 minute live slot

1. Slide 1–2: problem and solution (30 s).
2. Live demo: the 2-minute core from `DEMO_SCRIPT.md`.
3. Slides 7–8: what's done and next (15 s).

For a 15–20 minute slot, add B1–B4 (about 2 min each), the "Challenges" and "Limitations" sections of the README (about 3 min), and Q&A.
